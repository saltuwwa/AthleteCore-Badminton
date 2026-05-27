from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from video_analysis.player_tracking import FrameTrack


# COCO pose indices
_L_HIP, _R_HIP = 11, 12
_L_WRIST, _R_WRIST = 9, 10


@dataclass
class MotionSample:
    timestamp_sec: float
    track_id: int
    cx: float
    cy: float
    relative_speed: float
    forward_v: float
    lateral_v: float
    wrist_speed: float


def _centroid(keypoints: list[list[float]], bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    if keypoints and len(keypoints) > max(_L_HIP, _R_HIP):
        pts = []
        for idx in (_L_HIP, _R_HIP):
            x, y, c = keypoints[idx][0], keypoints[idx][1], keypoints[idx][2]
            if c >= 0.3:
                pts.append((x, y))
        if pts:
            return float(np.mean([p[0] for p in pts])), float(np.mean([p[1] for p in pts]))
    x1, y1, x2, y2 = bbox
    return (x1 + x2) / 2, (y1 + y2) / 2


def _wrist_speed(keypoints: list[list[float]], prev_kp: list[list[float]] | None, dt: float) -> float:
    if not keypoints or not prev_kp or dt <= 0:
        return 0.0
    dists = []
    for idx in (_L_WRIST, _R_WRIST):
        if idx >= len(keypoints) or idx >= len(prev_kp):
            continue
        if keypoints[idx][2] < 0.3 or prev_kp[idx][2] < 0.3:
            continue
        dx = keypoints[idx][0] - prev_kp[idx][0]
        dy = keypoints[idx][1] - prev_kp[idx][1]
        dists.append((dx * dx + dy * dy) ** 0.5)
    if not dists:
        return 0.0
    return float(max(dists) / dt)


def extract_motion_series(
    tracks: list[FrameTrack],
    *,
    track_ids: set[int],
    fps: float,
    frame_diagonal: float,
) -> dict[int, list[MotionSample]]:
    filtered = sorted(
        [t for t in tracks if t.track_id in track_ids],
        key=lambda t: (t.track_id, t.frame_index),
    )
    by_id: dict[int, list[FrameTrack]] = {}
    for t in filtered:
        by_id.setdefault(t.track_id, []).append(t)

    series: dict[int, list[MotionSample]] = {}
    diag = max(frame_diagonal, 1.0)

    for tid, frames in by_id.items():
        samples: list[MotionSample] = []
        prev: FrameTrack | None = None
        for fr in frames:
            cx, cy = _centroid(fr.keypoints, fr.bbox)
            dt = 1.0 / fps if prev is None else max(fr.timestamp_sec - prev.timestamp_sec, 1e-6)
            if prev is None:
                rel_speed = 0.0
                fwd, lat = 0.0, 0.0
            else:
                pcx, pcy = _centroid(prev.keypoints, prev.bbox)
                dx, dy = cx - pcx, cy - pcy
                dist = (dx * dx + dy * dy) ** 0.5
                rel_speed = float((dist / diag) / dt)
                fwd = float(dy / dt)
                lat = float(abs(dx) / dt)
            ws = _wrist_speed(fr.keypoints, prev.keypoints if prev else None, dt)
            samples.append(
                MotionSample(
                    timestamp_sec=fr.timestamp_sec,
                    track_id=tid,
                    cx=cx,
                    cy=cy,
                    relative_speed=rel_speed,
                    forward_v=fwd,
                    lateral_v=lat,
                    wrist_speed=ws,
                )
            )
            prev = fr
        series[tid] = samples
    return series


def partner_distance_series(
    series: dict[int, list[MotionSample]],
    track_ids: list[int],
    *,
    frame_diagonal: float,
) -> list[dict]:
    if len(track_ids) < 2:
        return []
    a_id, b_id = track_ids[0], track_ids[1]
    a = {round(s.timestamp_sec, 2): s for s in series.get(a_id, [])}
    b = {round(s.timestamp_sec, 2): s for s in series.get(b_id, [])}
    common = sorted(set(a.keys()) & set(b.keys()))
    diag = max(frame_diagonal, 1.0)
    points: list[dict] = []
    for ts in common:
        sa, sb = a[ts], b[ts]
        dist = ((sa.cx - sb.cx) ** 2 + (sa.cy - sb.cy) ** 2) ** 0.5 / diag
        points.append({"timestamp_sec": ts, "relative_distance": round(float(dist), 4)})
    return points
