from __future__ import annotations

import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile

from video_analysis.config import video_settings


def _video_dir(video_id: str) -> Path:
    return video_settings.storage_root / video_id


def video_paths(video_id: str) -> dict[str, Path]:
    base = _video_dir(video_id)
    return {
        "dir": base,
        "video": base / "source.mp4",
        "meta": base / "meta.json",
        "tracking": base / "tracking.json",
        "metrics": base / "metrics.json",
        "preview": base / "preview.jpg",
    }


def ensure_storage_root() -> None:
    video_settings.storage_root.mkdir(parents=True, exist_ok=True)


def load_meta(video_id: str) -> dict[str, Any]:
    paths = video_paths(video_id)
    if not paths["meta"].is_file():
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")
    return json.loads(paths["meta"].read_text(encoding="utf-8"))


def save_meta(video_id: str, meta: dict[str, Any]) -> None:
    paths = video_paths(video_id)
    paths["dir"].mkdir(parents=True, exist_ok=True)
    paths["meta"].write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


async def save_upload(file: UploadFile) -> dict[str, Any]:
    ensure_storage_root()
    filename = file.filename or "upload.mp4"
    ext = Path(filename).suffix.lower()
    if ext not in video_settings.extension_set:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format {ext}. Allowed: {sorted(video_settings.extension_set)}",
        )

    raw = await file.read()
    max_bytes = video_settings.max_video_mb * 1024 * 1024
    if len(raw) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"Video exceeds {video_settings.max_video_mb} MB limit",
        )
    if not raw:
        raise HTTPException(status_code=400, detail="Empty video file")

    video_id = str(uuid.uuid4())
    paths = video_paths(video_id)
    paths["dir"].mkdir(parents=True, exist_ok=True)
    paths["video"].write_bytes(raw)

    props = probe_video(paths["video"])
    meta = {
        "video_id": video_id,
        "filename": filename,
        "original_ext": ext,
        **props,
    }
    save_meta(video_id, meta)
    return meta


def probe_video(path: Path) -> dict[str, Any]:
    try:
        import cv2  # type: ignore[import-untyped]
    except ImportError as e:
        msg = "opencv-python-headless is required for video analysis (pip install opencv-python-headless)"
        try:
            from fastapi import HTTPException

            raise HTTPException(status_code=503, detail=msg) from e
        except ImportError:
            raise RuntimeError(msg) from e

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise HTTPException(status_code=422, detail="Could not read video file")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    duration_sec = frame_count / fps if fps > 0 and frame_count > 0 else None
    cap.release()

    return {
        "fps": fps,
        "frame_count": frame_count,
        "width": width,
        "height": height,
        "duration_sec": duration_sec,
    }


def register_video_from_path(
    source_path: Path,
    *,
    filename: str | None = None,
) -> dict[str, Any]:
    """Register a local file for pipeline/CLI without HTTP upload."""
    ensure_storage_root()
    if not source_path.is_file():
        raise FileNotFoundError(f"Video not found: {source_path}")

    video_id = str(uuid.uuid4())
    paths = video_paths(video_id)
    paths["dir"].mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, paths["video"])

    props = probe_video(paths["video"])
    meta = {
        "video_id": video_id,
        "filename": filename or source_path.name,
        "original_ext": source_path.suffix.lower(),
        "upload_time": datetime.now(UTC).isoformat(),
        **props,
    }
    save_meta(video_id, meta)
    return meta


def delete_video_artifacts(video_id: str) -> None:
    base = _video_dir(video_id)
    if base.is_dir():
        shutil.rmtree(base, ignore_errors=True)
