"""
Gameplay segment filtering — exclude replays, pauses, coach/spectator shots from metrics.

Works on tracked pose frames (no raw video required for heuristics).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Literal

FrameContext = Literal[
    "gameplay",
    "replay",
    "coach_or_spectator",
    "closeup",
    "scoreboard",
    "pause",
    "unknown",
]

IGNORE_REASON_MAP: dict[FrameContext, str] = {
    "replay": "replay_or_slow_motion",
    "coach_or_spectator": "coach_or_spectator_view",
    "closeup": "closeup",
    "scoreboard": "scoreboard",
    "pause": "pause_between_rallies",
    "unknown": "uncertain_excluded",
    "gameplay": "gameplay",
}

MIN_VALID_GAMEPLAY_RATIO = 0.25
LOW_RATIO_WARNING = "Недостаточно игровых моментов для точного анализа."


@dataclass
class FrameDetections:
    """All person detections in one video frame."""

    track_ids: list[int] = field(default_factory=list)
    bboxes: list[tuple[float, float, float, float]] = field(default_factory=list)
    keypoints: list[list[list[float]]] = field(default_factory=list)
    confidences: list[float] = field(default_factory=list)


@dataclass
class FrameRecord:
    frame_index: int
    timestamp_sec: float
    detections: FrameDetections
    ocr_text: str = ""


def _format_ts(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 60:02d}:{s % 60:02d}"


def _bbox_area(b: tuple[float, float, float, float]) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _bbox_center(b: tuple[float, float, float, float]) -> tuple[float, float]:
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def _has_usable_pose(kp: list[list[float]]) -> bool:
    if not kp or len(kp) < 13:
        return False
    visible = sum(1 for p in kp if len(p) >= 3 and p[2] >= 0.3)
    return visible >= 6


def _expected_on_court_count(match_type: str) -> int:
    if match_type in ("doubles", "mixed"):
        return 4
    return 2


def _in_court_area(
    bbox: tuple[float, float, float, float],
    *,
    width: float,
    height: float,
) -> bool:
    cx, cy = _bbox_center(bbox)
    if width <= 0 or height <= 0:
        return True
    nx, ny = cx / width, cy / height
    return 0.08 <= nx <= 0.92 and 0.12 <= ny <= 0.92


def _group_tracked_frames(
    tracked_frames: list[dict[str, Any]],
) -> list[FrameRecord]:
    by_idx: dict[int, FrameRecord] = {}
    for fr in tracked_frames:
        idx = int(fr.get("frame_index", 0))
        ts = float(fr.get("timestamp_sec", 0))
        if idx not in by_idx:
            by_idx[idx] = FrameRecord(
                frame_index=idx,
                timestamp_sec=ts,
                detections=FrameDetections(),
            )
        rec = by_idx[idx]
        tid = int(fr["track_id"])
        bbox = tuple(float(x) for x in fr["bbox"])
        rec.detections.track_ids.append(tid)
        rec.detections.bboxes.append(bbox)  # type: ignore[arg-type]
        rec.detections.keypoints.append(fr.get("keypoints") or [])
        rec.detections.confidences.append(float(fr.get("confidence", 0)))
    return sorted(by_idx.values(), key=lambda r: r.frame_index)


def classify_frame_context(
    frame: Any | None,
    detections: FrameDetections | list[dict[str, Any]],
    *,
    width: float = 1280,
    height: float = 720,
    ocr_text: str = "",
) -> FrameContext:
    """
    Classify a single frame's visual context from detections (and optional frame/OCR).
    """
    if isinstance(detections, list):
        fd = FrameDetections()
        for d in detections:
            fd.track_ids.append(int(d.get("track_id", 0)))
            b = d.get("bbox", [0, 0, 0, 0])
            fd.bboxes.append((float(b[0]), float(b[1]), float(b[2]), float(b[3])))
            fd.keypoints.append(d.get("keypoints") or [])
            fd.confidences.append(float(d.get("confidence", 0)))
        detections = fd

    fd = detections
    n = len(fd.bboxes)
    frame_area = max(width * height, 1.0)

    ocr = (ocr_text or "").lower()
    if re.search(r"\breplay\b|повтор|instant\s*replay", ocr, re.I):
        return "replay"

    if n == 0:
        return "pause"

    areas = [_bbox_area(b) for b in fd.bboxes]
    max_area_ratio = max(areas) / frame_area if areas else 0

    if n == 1 and max_area_ratio > 0.35:
        return "closeup"

    if max_area_ratio > 0.55:
        return "closeup"

    edge_count = 0
    for b in fd.bboxes:
        cx, _ = _bbox_center(b)
        if width > 0 and (cx < width * 0.06 or cx > width * 0.94):
            edge_count += 1
    if edge_count >= max(1, n // 2) and n <= 2:
        return "coach_or_spectator"

    if n >= 1:
        pose_ok = sum(1 for kp in fd.keypoints if _has_usable_pose(kp))
        if pose_ok == 0 and max(areas) / frame_area < 0.08:
            return "scoreboard"

    if n < 2:
        return "pause"

    court_count = sum(1 for b in fd.bboxes if _in_court_area(b, width=width, height=height))
    if court_count < min(2, _expected_on_court_count("singles")):
        return "unknown"

    return "gameplay"


def is_valid_gameplay_frame(
    frame: Any | None,
    detections: FrameDetections | list[dict[str, Any]],
    match_type: str,
    target_track_ids: list[int],
    *,
    width: float = 1280,
    height: float = 720,
    ocr_text: str = "",
) -> bool:
    ctx = classify_frame_context(
        frame, detections, width=width, height=height, ocr_text=ocr_text
    )
    if ctx != "gameplay":
        return False

    if isinstance(detections, list):
        fd = FrameDetections()
        for d in detections:
            fd.track_ids.append(int(d.get("track_id", 0)))
            b = d.get("bbox", [0, 0, 0, 0])
            fd.bboxes.append((float(b[0]), float(b[1]), float(b[2]), float(b[3])))
            fd.keypoints.append(d.get("keypoints") or [])
        detections = fd

    fd = detections
    expected = _expected_on_court_count(match_type)
    min_players = 2 if match_type == "singles" else 4
    if len(fd.bboxes) < min_players:
        return False

    targets = set(target_track_ids)
    if not any(tid in targets for tid in fd.track_ids):
        return False

    for b, kp in zip(fd.bboxes, fd.keypoints, strict=False):
        if not _in_court_area(b, width=width, height=height):
            continue
        if not _has_usable_pose(kp):
            continue
        return True

    return False


def detect_replay_or_slowmo(
    segment: list[FrameRecord],
    *,
    width: float = 1280,
    height: float = 720,
) -> bool:
    """Heuristic replay / slow-motion detection for a contiguous frame run."""
    if len(segment) < 3:
        return False

    for fr in segment:
        if re.search(r"\breplay\b|повтор", fr.ocr_text, re.I):
            return True

    frame_area = max(width * height, 1.0)
    max_ratios: list[float] = []
    for fr in segment:
        if not fr.detections.bboxes:
            max_ratios.append(0.0)
            continue
        max_ratios.append(max(_bbox_area(b) for b in fr.detections.bboxes) / frame_area)

    if max_ratios and max(max_ratios) > 0.45 and min(max_ratios) < 0.15:
        return True

    speeds: list[float] = []
    prev_center: tuple[float, float] | None = None
    for fr in segment:
        if not fr.detections.bboxes:
            prev_center = None
            continue
        largest = max(fr.detections.bboxes, key=_bbox_area)
        c = _bbox_center(largest)
        if prev_center is not None:
            dx = c[0] - prev_center[0]
            dy = c[1] - prev_center[1]
            speeds.append((dx * dx + dy * dy) ** 0.5)
        prev_center = c

    if speeds and mean(speeds) < max(width, height) * 0.002:
        return True

    contexts = [
        classify_frame_context(None, fr.detections, width=width, height=height, ocr_text=fr.ocr_text)
        for fr in segment
    ]
    if contexts.count("closeup") >= len(contexts) * 0.6:
        return True

    court_like = sum(1 for fr in segment if len(fr.detections.bboxes) >= 2)
    if court_like < len(segment) * 0.3:
        return True

    return False


def filter_gameplay_segments(
    tracked_frames: list[dict[str, Any]],
    *,
    match_type: str = "singles",
    target_track_ids: list[int] | None = None,
    width: float = 1280,
    height: float = 720,
    fps: float = 25.0,
) -> dict[str, Any]:
    """
    Partition timeline into valid gameplay vs ignored segments.
    Metrics must use only frames inside valid_segments.
    """
    target_track_ids = target_track_ids or []
    records = _group_tracked_frames(tracked_frames)
    if not records:
        return {
            "valid_segments": [],
            "ignored_segments": [],
            "valid_gameplay_ratio": 0.0,
            "analysis_confidence": 0.0,
            "warning": LOW_RATIO_WARNING,
            "valid_frame_indices": [],
        }

    frame_flags: list[tuple[FrameRecord, bool, FrameContext]] = []
    for fr in records:
        valid = is_valid_gameplay_frame(
            None,
            fr.detections,
            match_type,
            target_track_ids,
            width=width,
            height=height,
            ocr_text=fr.ocr_text,
        )
        ctx = classify_frame_context(
            None, fr.detections, width=width, height=height, ocr_text=fr.ocr_text
        )
        frame_flags.append((fr, valid, ctx))

    i = 0
    while i < len(frame_flags):
        fr, valid, ctx = frame_flags[i]
        if valid:
            i += 1
            continue
        j = i
        while j < len(frame_flags) and not frame_flags[j][1]:
            j += 1
        chunk = [frame_flags[k][0] for k in range(i, j)]
        if detect_replay_or_slowmo(chunk, width=width, height=height):
            for k in range(i, j):
                frame_flags[k] = (frame_flags[k][0], False, "replay")
        i = j

    valid_frames = sum(1 for _, v, _ in frame_flags if v)
    ratio = round(valid_frames / len(frame_flags), 2) if frame_flags else 0.0

    def _merge_segments(
        predicate,
    ) -> list[dict[str, str]]:
        segs: list[dict[str, str]] = []
        start_i: int | None = None
        for idx, (fr, valid, ctx) in enumerate(frame_flags):
            if predicate(valid, ctx, fr):
                if start_i is None:
                    start_i = idx
            else:
                if start_i is not None:
                    segs.append(
                        {
                            "start": _format_ts(frame_flags[start_i][0].timestamp_sec),
                            "end": _format_ts(frame_flags[idx - 1][0].timestamp_sec),
                        }
                    )
                    start_i = None
        if start_i is not None:
            segs.append(
                {
                    "start": _format_ts(frame_flags[start_i][0].timestamp_sec),
                    "end": _format_ts(frame_flags[-1][0].timestamp_sec),
                }
            )
        return segs

    valid_segments = _merge_segments(lambda v, _c, _f: v)

    ignored_segments: list[dict[str, str]] = []
    start_i = None
    dominant: FrameContext = "unknown"
    for idx, (fr, valid, ctx) in enumerate(frame_flags):
        if not valid:
            if start_i is None:
                start_i = idx
                dominant = ctx
            else:
                dominant = ctx
        else:
            if start_i is not None:
                ignored_segments.append(
                    {
                        "start": _format_ts(frame_flags[start_i][0].timestamp_sec),
                        "end": _format_ts(frame_flags[idx - 1][0].timestamp_sec),
                        "reason": IGNORE_REASON_MAP.get(dominant, "uncertain_excluded"),
                    }
                )
                start_i = None
    if start_i is not None:
        ignored_segments.append(
            {
                "start": _format_ts(frame_flags[start_i][0].timestamp_sec),
                "end": _format_ts(frame_flags[-1][0].timestamp_sec),
                "reason": IGNORE_REASON_MAP.get(dominant, "uncertain_excluded"),
            }
        )

    confidence = round(min(1.0, ratio * 1.1 + (0.1 if valid_segments else 0)), 2)
    warning = LOW_RATIO_WARNING if ratio < MIN_VALID_GAMEPLAY_RATIO else None

    valid_indices = [fr.frame_index for fr, v, _ in frame_flags if v]

    return {
        "valid_segments": valid_segments,
        "ignored_segments": ignored_segments,
        "valid_gameplay_ratio": ratio,
        "analysis_confidence": confidence,
        "warning": warning,
        "valid_frame_indices": valid_indices,
    }


def filter_tracking_payload(
    tracking: dict[str, Any],
    segment_result: dict[str, Any],
) -> dict[str, Any]:
    """Return tracking dict containing only valid gameplay frames."""
    valid_set = set(segment_result.get("valid_frame_indices") or [])
    if not valid_set:
        return {**tracking, "frames": []}
    frames = [f for f in tracking.get("frames", []) if int(f.get("frame_index", -1)) in valid_set]
    return {**tracking, "frames": frames, "segment_filter_applied": True}
