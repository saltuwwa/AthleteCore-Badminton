"""Heuristic enrichment for debug player / tracking reports."""

from __future__ import annotations

from statistics import mean
from typing import Any


def _bbox_center(bbox: list[float]) -> tuple[float, float]:
    return (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2


def guess_court_side(bbox: list[float], *, height: float) -> str:
    if height <= 0:
        return "unknown"
    _, cy = _bbox_center(bbox)
    ny = cy / height
    if ny < 0.42:
        return "far"
    if ny > 0.58:
        return "near"
    return "mid"


def guess_jersey_color(frame_bgr: Any, bbox: list[float]) -> str:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return "unknown"

    h, w = frame_bgr.shape[:2]
    x1, y1, x2, y2 = [int(max(0, v)) for v in bbox]
    x2, y2 = min(w, x2), min(h, y2)
    crop = frame_bgr[y1:y2, x1:x2]
    if crop.size == 0:
        return "unknown"
    torso = crop[int(crop.shape[0] * 0.15) : int(crop.shape[0] * 0.55)]
    if torso.size == 0:
        torso = crop
    hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
    h_mean = float(np.median(hsv[:, :, 0]))
    s_mean = float(np.median(hsv[:, :, 1]))
    v_mean = float(np.median(hsv[:, :, 2]))
    if v_mean < 45:
        return "black"
    if s_mean < 40:
        return "white" if v_mean > 160 else "gray"
    if h_mean < 10 or h_mean > 165:
        return "red"
    if 10 <= h_mean < 25:
        return "orange"
    if 25 <= h_mean < 40:
        return "yellow"
    if 40 <= h_mean < 85:
        return "green"
    if 85 <= h_mean < 130:
        return "blue"
    return "other"


def build_detected_players_debug(
    tracking: dict[str, Any],
    players_raw: list[dict[str, Any]],
    *,
    video_path: Any | None = None,
) -> list[dict[str, Any]]:
    width = float(tracking.get("width") or 1280)
    height = float(tracking.get("height") or 720)
    frame_bgr = None
    if video_path is not None:
        try:
            import cv2

            cap = cv2.VideoCapture(str(video_path))
            ok, frame_bgr = cap.read()
            cap.release()
            if not ok:
                frame_bgr = None
        except Exception:
            frame_bgr = None

    by_tid: dict[int, list[dict[str, Any]]] = {}
    for fr in tracking.get("frames", []):
        tid = int(fr["track_id"])
        by_tid.setdefault(tid, []).append(fr)

    out: list[dict[str, Any]] = []
    for p in players_raw:
        tid = int(p["track_id"])
        frames = by_tid.get(tid, [])
        pose_ok = 0
        for fr in frames:
            kp = fr.get("keypoints") or []
            vis = sum(1 for pt in kp if len(pt) >= 3 and pt[2] >= 0.3)
            if vis >= 6:
                pose_ok += 1
        bbox = [p["bbox"]["x1"], p["bbox"]["y1"], p["bbox"]["x2"], p["bbox"]["y2"]]
        jersey = "unknown"
        if frame_bgr is not None:
            jersey = guess_jersey_color(frame_bgr, bbox)
        out.append(
            {
                "track_id": tid,
                "label": p.get("label"),
                "bbox_samples": [f["bbox"] for f in frames[:5]],
                "jersey_color_guess": jersey,
                "court_side_guess": guess_court_side(bbox, height=height),
                "visibility_score": round(mean([f.get("confidence", 0) for f in frames]) if frames else 0, 3),
                "pose_detection_rate": round(pose_ok / len(frames), 3) if frames else 0,
                "sample_count": len(frames),
                "preview_crop_path": None,
            }
        )
    return out


def build_tracking_summary(
    tracking: dict[str, Any],
    target_track_ids: list[int],
) -> dict[str, Any]:
    frames = tracking.get("frames", [])
    if not frames:
        return {
            "track_id_switch_count": 0,
            "tracking_consistency_score": 0.0,
            "missing_frames_count": 0,
            "selected_track_coverage": 0.0,
        }

    frame_indices = sorted({int(f["frame_index"]) for f in frames})
    span = max(frame_indices) - min(frame_indices) + 1 if frame_indices else 1

    target_frames = {int(f["frame_index"]) for f in frames if int(f["track_id"]) in target_track_ids}
    coverage = len(target_frames) / span if span else 0

    switches = 0
    prev_tid: int | None = None
    for f in sorted(frames, key=lambda x: (x["frame_index"], x["track_id"])):
        tid = int(f["track_id"])
        if prev_tid is not None and tid != prev_tid:
            switches += 1
        prev_tid = tid

    expected = span * max(1, len(set(target_track_ids)))
    actual = sum(1 for f in frames if int(f["track_id"]) in target_track_ids)
    missing = max(0, expected - actual)

    return {
        "track_id_switch_count": switches,
        "tracking_consistency_score": round(min(1.0, coverage * 1.05), 3),
        "missing_frames_count": missing,
        "selected_track_coverage": round(coverage, 3),
        "unique_frame_indices": len(frame_indices),
        "total_detections": len(frames),
    }


def build_sampled_frames_debug(tracking: dict[str, Any]) -> dict[str, Any]:
    stride = int(tracking.get("frame_stride") or 1)
    fps = float(tracking.get("fps") or 25)
    effective_fps = fps / stride if stride else fps
    strategy = f"yolo_vid_stride={stride} (~{effective_fps:.1f} effective fps)"
    indices = sorted({int(f["frame_index"]) for f in tracking.get("frames", [])})
    timestamps = [round(i / fps, 3) for i in indices[:200]]
    return {
        "sampling_strategy": strategy,
        "total_frames_sampled": len(indices),
        "timestamps_used": timestamps,
        "preview_frame_paths": [],
    }
