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


def run_pose_tracking(
    video_path: Path,
    *,
    persist: bool = True,
    vid_stride: int | None = None,
    show_progress: bool = True,
) -> dict[str, Any]:
    """Run YOLO pose + ByteTrack/BoT-SORT on video. Returns serializable tracking payload."""
    model = _get_pose_model()
    meta_fps = 25.0
    total_frames = 0
    try:
        import cv2

        cap = cv2.VideoCapture(str(video_path))
        meta_fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        cap.release()
    except Exception:
        pass

    stride = vid_stride if vid_stride is not None else video_settings.yolo_vid_stride
    if show_progress:
        est = (total_frames // max(stride, 1)) if total_frames else "?"
        print(f"[tracking] stride={stride} ~{est} frames @ {meta_fps:.1f} fps", flush=True)

    results = model.track(
        source=str(video_path),
        persist=persist,
        tracker=video_settings.yolo_tracker,
        conf=video_settings.yolo_confidence,
        vid_stride=stride,
        stream=True,
        verbose=False,
    )

    frames: list[dict[str, Any]] = []
    width, height = 0, 0

    for frame_index, result in enumerate(results):
        if show_progress and frame_index > 0 and frame_index % 50 == 0:
            print(f"[tracking] processed {frame_index} sampled frames…", flush=True)
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

        ts = frame_index * stride / meta_fps

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
                    "frame_index": frame_index * stride,
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
        "frame_stride": stride,
        "frames": frames,
    }
    if show_progress:
        print(f"[tracking] done — {len(frames)} detections, {frame_index + 1} sampled frames", flush=True)
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


def ensure_tracking(
    video_id: str,
    *,
    vid_stride: int | None = None,
    show_progress: bool = True,
) -> dict[str, Any]:
    paths = video_paths(video_id)
    if paths["tracking"].is_file():
        if show_progress:
            print("[tracking] loaded cached tracking.json", flush=True)
        return load_tracking(video_id)
    if not paths["video"].is_file():
        raise FileNotFoundError(f"Video file missing for {video_id}")
    payload = run_pose_tracking(
        paths["video"],
        vid_stride=vid_stride,
        show_progress=show_progress,
    )
    save_tracking(video_id, payload)
    return payload


def aggregate_players(
    tracking: dict[str, Any],
    *,
    max_players: int | None = None,
    match_type: str = "singles",
    video_id: str | None = None,
    eval_output_path: Path | None = None,
    exclude_track_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Summarize track_ids: court filter, IoU dedup, near/far selection."""
    from video_analysis.track_postprocess import (
        save_player_selection_eval,
        select_players_from_tracking,
    )

    if max_players is None:
        max_players = 2 if match_type == "singles" else 4

    players, eval_doc = select_players_from_tracking(
        tracking,
        match_type=match_type,
        max_players=max_players,
        video_id=video_id,
        exclude_track_ids=exclude_track_ids,
    )

    if eval_output_path is not None:
        save_player_selection_eval(eval_doc, eval_output_path)
    elif video_id:
        from video_analysis.debug_report import debug_report_dir

        save_player_selection_eval(
            eval_doc,
            debug_report_dir(video_id) / "player_selection_eval.json",
        )

    return players


def render_preview_candidates_frame(
    video_path: Path,
    tracking: dict[str, Any],
    eval_doc: dict[str, Any],
    *,
    frame_index: int | None = None,
) -> tuple[str, int]:
    """Draw all candidate track decisions on one frame for debug review."""
    import cv2

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError("Cannot open video for preview candidates")

    target_idx = frame_index if frame_index is not None else 0
    # Prefer selected player's frame if available
    if frame_index is None:
        selected = eval_doc.get("selected_players") or []
        if selected:
            target_idx = int(selected[0].get("frame_index", 0))
    cap.set(cv2.CAP_PROP_POS_FRAMES, target_idx)
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise RuntimeError("Could not read preview candidates frame")

    decision_by_tid: dict[int, dict[str, Any]] = {}
    for d in eval_doc.get("track_decisions", []):
        tid = int(d.get("track_id", -1))
        if tid >= 0 and tid not in decision_by_tid:
            decision_by_tid[tid] = d
    selected_ids = {int(p["track_id"]) for p in (eval_doc.get("selected_players") or [])}

    for fr in tracking.get("frames", []):
        if int(fr.get("frame_index", -1)) != target_idx:
            continue
        tid = int(fr["track_id"])
        d = decision_by_tid.get(tid)
        if d is None:
            continue
        x1, y1, x2, y2 = [int(v) for v in fr["bbox"]]
        selected = tid in selected_ids
        color = (0, 220, 120) if selected else (60, 120, 240)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        fx = int((x1 + x2) / 2)
        fy = y2
        cv2.circle(frame, (fx, fy), 4, (0, 255, 255), -1)
        label = (
            f"id {tid} {d.get('side','?')} "
            f"f_in={d.get('footpoint_inside_green_court', d.get('footpoint_inside_court','?'))} "
            f"ov={d.get('court_overlap_ratio','?')}"
        )
        reason = str(d.get("reason", ""))[:36]
        cv2.putText(frame, label, (x1, max(y1 - 24, 16)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
        cv2.putText(frame, reason, (x1, max(y1 - 8, 28)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1, cv2.LINE_AA)

    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        raise RuntimeError("Failed to encode preview candidates image")
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}", target_idx


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
    colors = [(0, 200, 120), (255, 180, 0), (0, 180, 255), (255, 100, 200)]
    tid_color = {p["track_id"]: colors[i % len(colors)] for i, p in enumerate(players)}
    for fr in tracking.get("frames", []):
        if int(fr.get("frame_index", -1)) != target_idx:
            continue
        tid = int(fr["track_id"])
        if tid not in player_by_tid:
            continue
        label = player_by_tid[tid]["label"]
        x1, y1, x2, y2 = [int(v) for v in fr["bbox"]]
        color = tid_color.get(tid, (200, 200, 200))
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
