from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from video_analysis.config import video_settings
from video_analysis.preprocessing import video_paths


@dataclass
class FrameTrack:
    frame_index: int
    timestamp_sec: float
    track_id: int
    bbox: tuple[float, float, float, float]
    confidence: float
    keypoints: list[list[float]]


_model = None


def _get_pose_model():
    global _model
    if _model is None:
        try:
            from ultralytics import YOLO  # type: ignore[import-untyped]
        except ImportError as e:
            raise RuntimeError(
                "ultralytics is required. Install: pip install ultralytics"
            ) from e
        _model = YOLO(video_settings.yolo_pose_model)
    return _model


def run_pose_tracking(video_path: Path, *, persist: bool = True) -> dict[str, Any]:
    """Run YOLO pose + ByteTrack/BoT-SORT on video. Returns serializable tracking payload."""
    model = _get_pose_model()
    meta_fps = 25.0
    try:
        import cv2

        cap = cv2.VideoCapture(str(video_path))
        meta_fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
        cap.release()
    except Exception:
        pass

    results = model.track(
        source=str(video_path),
        persist=persist,
        tracker=video_settings.yolo_tracker,
        conf=video_settings.yolo_confidence,
        vid_stride=video_settings.yolo_vid_stride,
        verbose=False,
    )

    frames: list[dict[str, Any]] = []
    width, height = 0, 0

    for frame_index, result in enumerate(results):
        if result.orig_shape:
            height, width = int(result.orig_shape[0]), int(result.orig_shape[1])
        boxes = result.boxes
        kpts = result.keypoints
        if boxes is None or kpts is None:
            continue

        ids = boxes.id
        if ids is None:
            continue

        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        kid = ids.cpu().numpy().astype(int)
        kp_xy = kpts.xy.cpu().numpy()
        kp_conf = (
            kpts.conf.cpu().numpy()
            if kpts.conf is not None
            else np.ones((kp_xy.shape[0], kp_xy.shape[1]))
        )

        ts = frame_index * video_settings.yolo_vid_stride / meta_fps

        for i, tid in enumerate(kid):
            if i >= len(xyxy):
                break
            x1, y1, x2, y2 = [float(v) for v in xyxy[i]]
            kp_list: list[list[float]] = []
            for j in range(kp_xy.shape[1]):
                kp_list.append(
                    [
                        float(kp_xy[i, j, 0]),
                        float(kp_xy[i, j, 1]),
                        float(kp_conf[i, j]) if kp_conf is not None else 1.0,
                    ]
                )
            frames.append(
                {
                    "frame_index": frame_index * video_settings.yolo_vid_stride,
                    "timestamp_sec": round(ts, 3),
                    "track_id": int(tid),
                    "bbox": [x1, y1, x2, y2],
                    "confidence": float(confs[i]),
                    "keypoints": kp_list,
                }
            )

    payload = {
        "model": video_settings.yolo_pose_model,
        "tracker": video_settings.yolo_tracker,
        "fps": meta_fps,
        "width": width,
        "height": height,
        "frame_stride": video_settings.yolo_vid_stride,
        "frames": frames,
    }
    return payload


def save_tracking(video_id: str, payload: dict[str, Any]) -> Path:
    path = video_paths(video_id)["tracking"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def load_tracking(video_id: str) -> dict[str, Any]:
    path = video_paths(video_id)["tracking"]
    if not path.is_file():
        raise FileNotFoundError(f"No tracking for {video_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_tracking(video_id: str) -> dict[str, Any]:
    paths = video_paths(video_id)
    if paths["tracking"].is_file():
        return load_tracking(video_id)
    if not paths["video"].is_file():
        raise FileNotFoundError(f"Video file missing for {video_id}")
    payload = run_pose_tracking(paths["video"])
    save_tracking(video_id, payload)
    return payload


def aggregate_players(tracking: dict[str, Any], *, max_players: int = 4) -> list[dict[str, Any]]:
    """Summarize track_ids for player picker UI."""
    counts: dict[int, list[dict[str, Any]]] = {}
    for fr in tracking.get("frames", []):
        tid = int(fr["track_id"])
        counts.setdefault(tid, []).append(fr)

    ranked = sorted(counts.items(), key=lambda x: len(x[1]), reverse=True)[:max_players]
    players: list[dict[str, Any]] = []
    for rank, (tid, frames) in enumerate(ranked, start=1):
        best = max(frames, key=lambda f: f.get("confidence", 0))
        bbox = best["bbox"]
        players.append(
            {
                "track_id": tid,
                "label": f"Player {rank}",
                "bbox": {
                    "x1": bbox[0],
                    "y1": bbox[1],
                    "x2": bbox[2],
                    "y2": bbox[3],
                },
                "confidence": float(best.get("confidence", 0)),
                "frame_index": int(best.get("frame_index", 0)),
                "sample_count": len(frames),
            }
        )
    return players


def render_preview_frame(
    video_path: Path,
    tracking: dict[str, Any],
    players: list[dict[str, Any]],
    *,
    frame_index: int | None = None,
) -> tuple[str, int]:
    import cv2

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError("Cannot open video for preview")

    target_idx = frame_index
    if target_idx is None and players:
        target_idx = int(players[0].get("frame_index", 0))
    if target_idx is None:
        target_idx = 0

    cap.set(cv2.CAP_PROP_POS_FRAMES, target_idx)
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise RuntimeError("Could not read preview frame")

    player_by_tid = {p["track_id"]: p for p in players}
    for fr in tracking.get("frames", []):
        if int(fr.get("frame_index", -1)) != target_idx:
            continue
        tid = int(fr["track_id"])
        if tid not in player_by_tid:
            continue
        label = player_by_tid[tid]["label"]
        x1, y1, x2, y2 = [int(v) for v in fr["bbox"]]
        color = (0, 200, 120) if tid == players[0]["track_id"] else (255, 180, 0)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            frame,
            f"{label} (id {tid})",
            (x1, max(y1 - 8, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2,
            cv2.LINE_AA,
        )

    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        raise RuntimeError("Failed to encode preview")
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}", target_idx


def frame_tracks_from_payload(tracking: dict[str, Any]) -> list[FrameTrack]:
    out: list[FrameTrack] = []
    for fr in tracking.get("frames", []):
        bbox = fr["bbox"]
        out.append(
            FrameTrack(
                frame_index=int(fr["frame_index"]),
                timestamp_sec=float(fr["timestamp_sec"]),
                track_id=int(fr["track_id"]),
                bbox=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
                confidence=float(fr.get("confidence", 0)),
                keypoints=fr.get("keypoints") or [],
            )
        )
    return out
