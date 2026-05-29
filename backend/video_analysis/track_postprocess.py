"""
Post-process YOLO/ByteTrack: court polygon, footpoint validation, IoU dedup, near/far selection.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, median
from typing import Any, Literal

Side = Literal["near", "far", "unknown"]

# Normalized GREEN playable court polygon (stricter; excludes blue/red side zones)
PLAYABLE_COURT_POLYGON: list[tuple[float, float]] = [
    (0.29, 0.31),  # far left corner
    (0.73, 0.31),  # far right corner
    (0.78, 0.87),  # near right corner
    (0.26, 0.87),  # near left corner
]

# Lower / upper halves of playable court for footpoint checks
NEAR_COURT_POLYGON: list[tuple[float, float]] = [
    (0.27, 0.54),
    (0.77, 0.54),
    (0.79, 0.87),
    (0.25, 0.87),
]
FAR_COURT_POLYGON: list[tuple[float, float]] = [
    (0.29, 0.31),
    (0.73, 0.31),
    (0.76, 0.54),
    (0.26, 0.54),
]

IOU_MERGE_THRESHOLD = 0.45
TEMPORAL_IOU_MERGE_THRESHOLD = 0.38
MIN_POSE_FRAME_RATIO = 0.20
MIN_SAMPLES = 8
FAR_MIN_SAMPLES_WARN = 30
MARGIN_CX_SOFT = 0.25  # penalty below/above, not hard reject
LEFT_SIDE_OFFICIAL_X = 0.30


@dataclass
class TrackStats:
    track_id: int
    sample_count: int = 0
    mean_confidence: float = 0.0
    pose_frame_ratio: float = 0.0
    median_bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    median_cx: float = 0.0
    median_cy: float = 0.0
    median_foot_x: float = 0.0
    median_foot_y: float = 0.0
    footpoint_inside_court: float = 0.0
    footpoint_inside_green_court: float = 0.0
    court_overlap_ratio: float = 0.0
    foot_in_near_court_ratio: float = 0.0
    foot_in_far_court_ratio: float = 0.0
    margin_penalty: float = 1.0
    seated_official_penalty: float = 1.0
    court_validity_score: float = 0.0
    legacy_score: float = 0.0
    median_area_ratio: float = 0.0
    side: Side = "unknown"
    bboxes_by_frame: dict[int, list[float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "sample_count": self.sample_count,
            "mean_confidence": round(self.mean_confidence, 4),
            "pose_frame_ratio": round(self.pose_frame_ratio, 4),
            "median_bbox": list(self.median_bbox),
            "median_cx_norm": round(self.median_cx, 4),
            "median_cy_norm": round(self.median_cy, 4),
            "median_foot_x_norm": round(self.median_foot_x, 4),
            "median_foot_y_norm": round(self.median_foot_y, 4),
            "footpoint_inside_court": round(self.footpoint_inside_court, 4),
            "footpoint_inside_green_court": round(self.footpoint_inside_green_court, 4),
            "court_overlap_ratio": round(self.court_overlap_ratio, 4),
            "foot_in_near_court_ratio": round(self.foot_in_near_court_ratio, 4),
            "foot_in_far_court_ratio": round(self.foot_in_far_court_ratio, 4),
            "margin_penalty": round(self.margin_penalty, 4),
            "seated_official_penalty": round(self.seated_official_penalty, 4),
            "court_validity_score": round(self.court_validity_score, 4),
            "side": self.side,
        }


def bbox_iou(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = max(0.0, (a[2] - a[0]) * (a[3] - a[1]))
    area_b = max(0.0, (b[2] - b[0]) * (b[3] - b[1]))
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def point_in_polygon(px: float, py: float, polygon: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if ((y1 > py) != (y2 > py)) and (
            px < (x2 - x1) * (py - y1) / (y2 - y1 + 1e-12) + x1
        ):
            inside = not inside
    return inside


def footpoint_norm(bbox: list[float], width: float, height: float) -> tuple[float, float]:
    if width <= 0 or height <= 0:
        return 0.5, 1.0
    foot_x = (bbox[0] + bbox[2]) / 2.0
    foot_y = bbox[3]
    return foot_x / width, foot_y / height


def _bbox_sample_overlap(bbox: list[float], width: float, height: float, polygon: list[tuple[float, float]]) -> float:
    """Fraction of bbox sample points (corners + foot) inside polygon."""
    fx, fy = footpoint_norm(bbox, width, height)
    x1, y1, x2, y2 = bbox[0] / width, bbox[1] / height, bbox[2] / width, bbox[3] / height
    pts = [(fx, fy), (x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    inside = sum(1 for px, py in pts if point_in_polygon(px, py, polygon))
    return inside / len(pts)


def _has_pose(kp: list[list[float]]) -> bool:
    if not kp or len(kp) < 13:
        return False
    return sum(1 for p in kp if len(p) >= 3 and p[2] >= 0.3) >= 6


def _margin_penalty(cx_norm: float) -> float:
    if cx_norm < MARGIN_CX_SOFT:
        # Stronger penalty closer to edge (judge seats)
        return max(0.08, cx_norm / MARGIN_CX_SOFT * 0.35)
    if cx_norm > (1.0 - MARGIN_CX_SOFT):
        excess = cx_norm - (1.0 - MARGIN_CX_SOFT)
        return max(0.25, 1.0 - excess * 2.5)
    return 1.0


def _in_side_official_area(stats: "TrackStats") -> bool:
    """Hard reject for left referee bench / side officials area."""
    return (
        stats.median_cx < LEFT_SIDE_OFFICIAL_X
        and 0.38 <= stats.median_cy <= 0.78
        and stats.foot_in_near_court_ratio < 0.30
    )


def _classify_side(cy_norm: float, foot_y_norm: float) -> Side:
    if cy_norm < 0.44 and foot_y_norm < 0.55:
        return "far"
    if cy_norm > 0.56 or foot_y_norm > 0.62:
        return "near"
    return "unknown"


def _seated_official_penalty(stats: "TrackStats") -> float:
    """Penalize seated sideline officials (e.g. track 173)."""
    if stats.footpoint_inside_court >= 0.45 and stats.court_overlap_ratio >= 0.40:
        return 1.0
    pen = 1.0
    if stats.median_cx < 0.28:
        pen *= 0.12
    if stats.footpoint_inside_court < 0.25:
        pen *= 0.15
    if stats.court_overlap_ratio < 0.35:
        pen *= 0.25
    # Seated: wide bbox, mid height, foot not deep on court
    x1, y1, x2, y2 = stats.median_bbox
    h = max(y2 - y1, 1.0)
    w = max(x2 - x1, 1.0)
    aspect = w / h
    if aspect > 0.55 and 0.42 < stats.median_cy < 0.62 and stats.foot_in_near_court_ratio < 0.2:
        pen *= 0.2
    return pen


def _compute_court_validity(stats: TrackStats, side: Side) -> float:
    base = stats.footpoint_inside_court * 0.55 + stats.court_overlap_ratio * 0.45
    base *= stats.margin_penalty * stats.seated_official_penalty

    if side == "near":
        if stats.median_cy > 0.65:
            base *= 1.25
        if stats.foot_in_near_court_ratio > 0.5:
            base *= 1.2
        if stats.median_cy < 0.58:
            base *= 0.35
        if stats.foot_in_near_court_ratio < 0.15:
            base *= 0.2
    elif side == "far":
        if stats.median_cy < 0.48:
            base *= 1.2
        if stats.foot_in_far_court_ratio > 0.5:
            base *= 1.2
        if stats.median_cy > 0.55:
            base *= 0.4

    sample_factor = min(1.0, math.log1p(stats.sample_count) / math.log1p(80))
    conf_factor = 0.5 + stats.mean_confidence * 0.5
    return base * sample_factor * conf_factor


def _build_track_stats(tracking: dict[str, Any]) -> dict[int, TrackStats]:
    width = float(tracking.get("width") or 1280)
    height = float(tracking.get("height") or 720)
    frame_area = max(width * height, 1.0)

    by_tid: dict[int, list[dict[str, Any]]] = {}
    for fr in tracking.get("frames", []):
        tid = int(fr["track_id"])
        by_tid.setdefault(tid, []).append(fr)

    stats_map: dict[int, TrackStats] = {}
    for tid, frames in by_tid.items():
        confs: list[float] = []
        pose_hits = 0
        bboxes: list[list[float]] = []
        bboxes_by_frame: dict[int, list[float]] = {}
        foot_inside_playable: list[float] = []
        overlap_ratios: list[float] = []
        foot_near: list[float] = []
        foot_far: list[float] = []

        for fr in frames:
            bbox = fr["bbox"]
            confs.append(float(fr.get("confidence", 0)))
            bboxes.append(bbox)
            bboxes_by_frame[int(fr["frame_index"])] = bbox
            fx, fy = footpoint_norm(bbox, width, height)
            foot_inside_playable.append(
                1.0 if point_in_polygon(fx, fy, PLAYABLE_COURT_POLYGON) else 0.0
            )
            foot_near.append(1.0 if point_in_polygon(fx, fy, NEAR_COURT_POLYGON) else 0.0)
            foot_far.append(1.0 if point_in_polygon(fx, fy, FAR_COURT_POLYGON) else 0.0)
            overlap_ratios.append(_bbox_sample_overlap(bbox, width, height, PLAYABLE_COURT_POLYGON))
            if _has_pose(fr.get("keypoints") or []):
                pose_hits += 1

        n = len(frames)
        if n == 0:
            continue

        foot_xs = [(b[0] + b[2]) / 2 / width for b in bboxes]
        foot_ys = [b[3] / height for b in bboxes]
        xs = foot_xs
        ys = [(b[1] + b[3]) / 2 / height for b in bboxes]
        areas = [(b[2] - b[0]) * (b[3] - b[1]) / frame_area for b in bboxes]

        med_bbox = (
            float(median([b[0] for b in bboxes])),
            float(median([b[1] for b in bboxes])),
            float(median([b[2] for b in bboxes])),
            float(median([b[3] for b in bboxes])),
        )
        cx_norm = float(median(xs))
        cy_norm = float(median(ys))
        foot_x_norm = float(median(foot_xs))
        foot_y_norm = float(median(foot_ys))

        stats = TrackStats(
            track_id=tid,
            sample_count=n,
            mean_confidence=mean(confs) if confs else 0.0,
            pose_frame_ratio=pose_hits / n,
            median_bbox=med_bbox,
            median_cx=cx_norm,
            median_cy=cy_norm,
            median_foot_x=foot_x_norm,
            median_foot_y=foot_y_norm,
            footpoint_inside_court=mean(foot_inside_playable),
            footpoint_inside_green_court=mean(foot_inside_playable),
            court_overlap_ratio=mean(overlap_ratios),
            foot_in_near_court_ratio=mean(foot_near),
            foot_in_far_court_ratio=mean(foot_far),
            margin_penalty=_margin_penalty(cx_norm),
            median_area_ratio=float(median(areas)) if areas else 0.0,
            bboxes_by_frame=bboxes_by_frame,
        )
        stats.seated_official_penalty = _seated_official_penalty(stats)
        stats.side = _classify_side(cy_norm, foot_y_norm)
        stats.court_validity_score = _compute_court_validity(stats, stats.side)
        stats.legacy_score = n * stats.mean_confidence * (0.5 + stats.footpoint_inside_court)
        stats_map[tid] = stats

    return stats_map


def _temporal_iou(a: TrackStats, b: TrackStats) -> float:
    common = set(a.bboxes_by_frame) & set(b.bboxes_by_frame)
    if not common:
        return 0.0
    ious = [
        bbox_iou(tuple(a.bboxes_by_frame[f]), tuple(b.bboxes_by_frame[f]))
        for f in common
    ]
    return mean(ious) if ious else 0.0


def _should_merge(a: TrackStats, b: TrackStats) -> tuple[bool, float, str]:
    rep_iou = bbox_iou(a.median_bbox, b.median_bbox)
    t_iou = _temporal_iou(a, b)
    if rep_iou >= IOU_MERGE_THRESHOLD:
        return True, rep_iou, "median_bbox_iou"
    if t_iou >= TEMPORAL_IOU_MERGE_THRESHOLD:
        return True, t_iou, "temporal_mean_iou"
    if a.side == b.side and a.side != "unknown" and rep_iou >= 0.30:
        return True, rep_iou, "same_side_overlap"
    return False, max(rep_iou, t_iou), "below_threshold"


def _pick_winner(a: TrackStats, b: TrackStats) -> tuple[TrackStats, TrackStats]:
    if a.court_validity_score > b.court_validity_score or (
        a.court_validity_score == b.court_validity_score and a.sample_count >= b.sample_count
    ):
        return a, b
    return b, a


def _filter_eligible(stats_map: dict[int, TrackStats]) -> tuple[list[TrackStats], list[dict[str, Any]]]:
    eligible: list[TrackStats] = []
    discarded: list[dict[str, Any]] = []

    for stats in stats_map.values():
        reason = None
        if stats.sample_count < MIN_SAMPLES:
            reason = "too_few_samples"
        elif stats.pose_frame_ratio < MIN_POSE_FRAME_RATIO:
            reason = "insufficient_pose"
        elif stats.footpoint_inside_court < 0.15 and stats.court_overlap_ratio < 0.20:
            reason = "foot_and_bbox_outside_playable_court"
        elif stats.court_overlap_ratio < 0.12:
            reason = "mostly_outside_court_polygon"
        elif _in_side_official_area(stats):
            reason = "side_official_area"
        elif stats.seated_official_penalty < 0.18:
            reason = "likely_seated_official_or_spectator"
        elif stats.court_validity_score < 0.03:
            reason = "court_validity_too_low"
        elif stats.median_area_ratio > 0.42:
            reason = "closeup_too_large"
        elif stats.median_area_ratio < 0.004:
            reason = "bbox_too_small"

        if reason:
            discarded.append({**stats.to_dict(), "decision": "discarded", "reason": reason})
        else:
            eligible.append(stats)
    return eligible, discarded


def _merge_duplicates(
    eligible: list[TrackStats],
) -> tuple[list[TrackStats], list[dict[str, Any]], dict[str, float], set[int]]:
    merge_events: list[dict[str, Any]] = []
    pairwise: dict[str, float] = {}
    removed_ids: set[int] = set()

    sorted_tracks = sorted(eligible, key=lambda s: s.court_validity_score, reverse=True)
    clusters: list[TrackStats] = []
    used: set[int] = set()

    for i, ta in enumerate(sorted_tracks):
        for tb in sorted_tracks[i + 1 :]:
            key = f"{ta.track_id}_{tb.track_id}"
            merge, iou_val, basis = _should_merge(ta, tb)
            pairwise[key] = round(iou_val, 4)

    for ta in sorted_tracks:
        if ta.track_id in used:
            continue
        cluster_rep = ta
        used.add(ta.track_id)
        for tb in sorted_tracks:
            if tb.track_id in used:
                continue
            merge, iou_val, basis = _should_merge(cluster_rep, tb)
            if merge:
                winner, loser = _pick_winner(cluster_rep, tb)
                cluster_rep = winner
                used.add(loser.track_id)
                removed_ids.add(loser.track_id)
                merge_events.append(
                    {
                        "kept_track_id": winner.track_id,
                        "merged_track_id": loser.track_id,
                        "iou": round(iou_val, 4),
                        "basis": basis,
                        "reason": "cluster_merge",
                    }
                )
        clusters.append(cluster_rep)

    return clusters, merge_events, pairwise, removed_ids


def _best_on_side(candidates: list[TrackStats], side: Side) -> TrackStats | None:
    pool = [c for c in candidates if c.side == side]
    if not pool:
        return None
    return max(pool, key=lambda s: s.court_validity_score)


def _select_singles(clusters: list[TrackStats]) -> tuple[list[TrackStats], list[dict[str, Any]]]:
    selected: list[TrackStats] = []
    decisions: list[dict[str, Any]] = []

    bn = _best_on_side(clusters, "near")
    bf = _best_on_side(clusters, "far")

    if bn is None:
        near_pool = sorted(
            [c for c in clusters if c.median_cy > 0.58 or c.foot_in_near_court_ratio > 0.3],
            key=lambda s: s.court_validity_score,
            reverse=True,
        )
        bn = near_pool[0] if near_pool else None

    if bf is None:
        far_pool = sorted(
            [c for c in clusters if c.median_cy < 0.50 or c.foot_in_far_court_ratio > 0.3],
            key=lambda s: s.court_validity_score,
            reverse=True,
        )
        bf = far_pool[0] if far_pool else None

    if bn and _in_side_official_area(bn):
        near_pool = sorted(
            [c for c in clusters if c.track_id != bn.track_id and (c.median_cy > 0.60 or c.foot_in_near_court_ratio > 0.35)],
            key=lambda s: s.court_validity_score,
            reverse=True,
        )
        if near_pool:
            decisions.append(
                {
                    **bn.to_dict(),
                    "decision": "discarded",
                    "reason": "side_official_area_hard_sanity_check",
                }
            )
            bn = near_pool[0]

    if bn:
        selected.append(bn)
        decisions.append(
            {**bn.to_dict(), "decision": "selected", "reason": "court_validity_best_near"}
        )
    if bf and (bf.track_id not in {s.track_id for s in selected}):
        selected.append(bf)
        decisions.append(
            {**bf.to_dict(), "decision": "selected", "reason": "court_validity_best_far"}
        )

    if len(selected) < 2:
        for c in sorted(clusters, key=lambda s: s.court_validity_score, reverse=True):
            if len(selected) >= 2:
                break
            if c.track_id not in {s.track_id for s in selected}:
                selected.append(c)
                decisions.append(
                    {**c.to_dict(), "decision": "selected", "reason": "court_validity_fallback"}
                )

    for c in clusters:
        if c.track_id not in {s.track_id for s in selected}:
            decisions.append(
                {**c.to_dict(), "decision": "discarded", "reason": "lower_court_validity_on_side"}
            )

    return selected[:2], decisions


def _select_doubles(clusters: list[TrackStats], max_players: int) -> tuple[list[TrackStats], list[dict[str, Any]]]:
    near = sorted(
        [c for c in clusters if c.side == "near"],
        key=lambda s: s.court_validity_score,
        reverse=True,
    )
    far = sorted(
        [c for c in clusters if c.side == "far"],
        key=lambda s: s.court_validity_score,
        reverse=True,
    )
    selected: list[TrackStats] = []
    decisions: list[dict[str, Any]] = []

    for c in near[:2]:
        selected.append(c)
        decisions.append({**c.to_dict(), "decision": "selected", "reason": "near_court_validity"})
    for c in far[:2]:
        if len(selected) < max_players:
            selected.append(c)
            decisions.append({**c.to_dict(), "decision": "selected", "reason": "far_court_validity"})

    for c in clusters:
        if c.track_id not in {s.track_id for s in selected}:
            decisions.append({**c.to_dict(), "decision": "discarded", "reason": "lower_court_validity"})

    return selected[:max_players], decisions


def build_selection_warnings(
    players: list[dict[str, Any]],
    stats_by_id: dict[int, TrackStats],
) -> list[str]:
    warnings: list[str] = []
    for p in players:
        tid = int(p["track_id"])
        st = stats_by_id.get(tid)
        if st is None:
            warnings.append(f"track_id={tid}: missing stats")
            continue
        label = p.get("label", str(tid))
        if p.get("court_side") == "near" and st.median_cx < LEFT_SIDE_OFFICIAL_X:
            warnings.append(
                f"WARNING [{label} id={tid}]: near player cx_norm={st.median_cx:.2f} "
                f"< {LEFT_SIDE_OFFICIAL_X} — likely sideline judge/spectator, not on-court athlete"
            )
        if st.footpoint_inside_court < 0.35:
            warnings.append(
                f"WARNING [{label} id={tid}]: footpoint_inside_court={st.footpoint_inside_court:.2f} "
                f"— foot often outside playable court polygon"
            )
        if st.court_overlap_ratio < 0.25:
            warnings.append(
                f"WARNING [{label} id={tid}]: court_overlap_ratio={st.court_overlap_ratio:.2f} "
                f"— bbox mostly outside playable court"
            )
        if p.get("court_side") == "far" and st.sample_count < FAR_MIN_SAMPLES_WARN:
            warnings.append(
                f"WARNING [{label} id={tid}]: sample_count={st.sample_count} < {FAR_MIN_SAMPLES_WARN} "
                f"— low_stability far-side track; metrics may be noisy"
            )
            p["low_stability"] = True
        if st.seated_official_penalty < 0.35:
            warnings.append(
                f"WARNING [{label} id={tid}]: likely seated official "
                f"(seated_penalty={st.seated_official_penalty:.2f})"
            )
    return warnings


def _stats_to_player(stats: TrackStats, rank: int, label: str | None = None) -> dict[str, Any]:
    x1, y1, x2, y2 = stats.median_bbox
    best_frame = max(stats.bboxes_by_frame.keys()) if stats.bboxes_by_frame else 0
    side_label = label or f"Player {rank} ({stats.side})"
    player = {
        "track_id": stats.track_id,
        "label": side_label,
        "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        "confidence": stats.mean_confidence,
        "frame_index": best_frame,
        "sample_count": stats.sample_count,
        "court_side": stats.side,
        "footpoint_inside_court": round(stats.footpoint_inside_court, 4),
        "footpoint_inside_green_court": round(stats.footpoint_inside_green_court, 4),
        "court_overlap_ratio": round(stats.court_overlap_ratio, 4),
        "court_validity_score": round(stats.court_validity_score, 4),
        "median_cx_norm": round(stats.median_cx, 4),
        "median_cy_norm": round(stats.median_cy, 4),
        "low_stability": stats.sample_count < FAR_MIN_SAMPLES_WARN,
    }
    return player


def select_players_from_tracking(
    tracking: dict[str, Any],
    *,
    match_type: str = "singles",
    max_players: int | None = None,
    video_id: str | None = None,
    exclude_track_ids: list[int] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if max_players is None:
        max_players = 2 if match_type == "singles" else 4

    stats_map = _build_track_stats(tracking)
    excluded = set(exclude_track_ids or [])
    excluded_decisions: list[dict[str, Any]] = []
    if excluded:
        for tid in list(stats_map.keys()):
            if tid in excluded:
                excluded_decisions.append(
                    {**stats_map[tid].to_dict(), "decision": "discarded", "reason": "manual_exclude_track_id"}
                )
                stats_map.pop(tid, None)
    raw_tracks = [s.to_dict() for s in stats_map.values()]
    eligible, pre_discarded = _filter_eligible(stats_map)
    clusters, merge_events, pairwise_iou, removed_ids = _merge_duplicates(eligible)

    if match_type == "singles":
        selected_stats, side_decisions = _select_singles(clusters)
    else:
        selected_stats, side_decisions = _select_doubles(clusters, max_players)

    labels = {"near": "Near court", "far": "Far court"}
    players: list[dict[str, Any]] = []
    for i, st in enumerate(selected_stats, start=1):
        players.append(_stats_to_player(st, i, labels.get(st.side, f"Player {i}")))

    warnings = build_selection_warnings(players, stats_map)

    eval_doc = {
        "video_id": video_id,
        "match_type": match_type,
        "raw_track_count": len(stats_map),
        "eligible_track_count": len(eligible),
        "cluster_count_after_merge": len(clusters),
        "final_player_count": len(players),
        "duplicate_tracks_removed": len(removed_ids),
        "merge_event_count": len(merge_events),
        "removed_track_ids": sorted(removed_ids),
        "selection_warnings": warnings,
        "selected_players": players,
        "track_decisions": excluded_decisions + pre_discarded + side_decisions,
        "merge_events": merge_events,
        "debug": {
            "raw_tracks": raw_tracks,
            "pairwise_iou": pairwise_iou,
            "merge_events": merge_events,
            "discarded_pre_merge": pre_discarded,
            "final_selected": [p["track_id"] for p in players],
        },
    }
    return players, eval_doc


def save_player_selection_eval(eval_doc: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(eval_doc, ensure_ascii=False, indent=2), encoding="utf-8")
