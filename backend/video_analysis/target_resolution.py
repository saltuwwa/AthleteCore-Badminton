"""Resolve target vs opponent track IDs for singles (manual override + court_side)."""

from __future__ import annotations

from typing import Any, Literal

from video_analysis.track_postprocess import TrackStats, _build_track_stats

Side = Literal["near", "far", "unknown"]


def _side_for_track(stats: TrackStats) -> Side:
    return stats.side if stats.side in ("near", "far") else "unknown"


def _infer_side_from_geometry(stats: TrackStats) -> Side:
    if stats.median_cy > 0.58 or stats.foot_in_near_court_ratio > 0.35:
        return "near"
    if stats.median_cy < 0.48 or stats.foot_in_far_court_ratio > 0.35:
        return "far"
    return "unknown"


def resolve_singles_target_tracks(
    tracking: dict[str, Any],
    candidate_track_ids: list[int],
    *,
    target_court_side: Side | None = None,
    target_label: str | None = None,
    exclude_track_ids: list[int] | None = None,
) -> dict[str, Any]:
    """
    Pick target athlete track from candidates using court_side when provided.

    Returns target_player_id (for metrics/memory), opponent_player_id (context only),
    and the single-element target_track_ids list for the analyze API.
    """
    stats_map = _build_track_stats(tracking)
    candidates: list[TrackStats] = []
    missing: list[int] = []
    excluded = set(exclude_track_ids or [])
    for tid in candidate_track_ids:
        if tid in excluded:
            missing.append(tid)
            continue
        if tid in stats_map:
            candidates.append(stats_map[tid])
        else:
            missing.append(tid)

    if not candidates:
        raise ValueError(f"No tracking stats for track ids: {candidate_track_ids}")

    side_by_tid: dict[int, Side] = {}
    for st in candidates:
        side = _side_for_track(st)
        if side == "unknown":
            side = _infer_side_from_geometry(st)
        side_by_tid[st.track_id] = side

    target_id: int
    opponent_id: int | None = None
    resolution = "first_candidate"

    if target_court_side in ("near", "far") and len(candidates) >= 1:
        matching = [st for st in candidates if side_by_tid[st.track_id] == target_court_side]
        if matching:
            best = max(matching, key=lambda s: s.court_validity_score)
            target_id = best.track_id
            resolution = f"court_side_match_{target_court_side}"
        else:
            # No exact side label — pick by geometry toward requested side
            if target_court_side == "far":
                best = min(candidates, key=lambda s: (s.median_cy, -s.court_validity_score))
            else:
                best = max(candidates, key=lambda s: (s.median_cy, s.court_validity_score))
            target_id = best.track_id
            resolution = f"geometry_fallback_{target_court_side}"
    elif len(candidates) == 1:
        target_id = candidates[0].track_id
        resolution = "single_candidate"
    else:
        target_id = max(candidates, key=lambda s: s.court_validity_score).track_id
        resolution = "highest_court_validity"

    others = [st.track_id for st in candidates if st.track_id != target_id]
    opponent_id = others[0] if others else None

    return {
        "target_player_id": target_id,
        "opponent_player_id": opponent_id,
        "target_label": target_label,
        "target_court_side": target_court_side,
        "target_track_ids": [target_id],
        "candidate_track_ids": candidate_track_ids,
        "candidate_sides": {str(tid): side_by_tid[tid] for tid in side_by_tid},
        "resolution": resolution,
        "missing_track_ids": missing,
    }


def format_target_resolution_summary(resolved: dict[str, Any]) -> str:
    lines = [
        "--- Target resolution (singles) ---",
        f"target_player_id: {resolved['target_player_id']}",
        f"opponent_player_id: {resolved.get('opponent_player_id')}",
        f"target_label: {resolved.get('target_label')}",
        f"target_court_side: {resolved.get('target_court_side')}",
        f"candidate_track_ids: {resolved.get('candidate_track_ids')}",
        f"candidate_sides: {resolved.get('candidate_sides')}",
        f"resolution: {resolved.get('resolution')}",
        f"analyze will use target_track_ids: {resolved.get('target_track_ids')}",
    ]
    return "\n".join(lines)
