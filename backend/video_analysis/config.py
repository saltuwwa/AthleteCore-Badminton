from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ENV_FILE = _BACKEND_DIR / ".env"


class VideoAnalysisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    video_storage_dir: str = str(_BACKEND_DIR / "data" / "videos")
    yolo_pose_model: str = "yolov8n-pose.pt"
    yolo_tracker: str = "bytetrack.yaml"
    yolo_confidence: float = 0.35
    yolo_vid_stride: int = 2
    detect_max_frames: int = 120
    max_video_mb: int = 250
    allowed_video_extensions: str = ".mp4,.mov,.avi,.mkv,.webm"

    google_api_key: str | None = None
    # Preferred explicit setting for video feedback model
    video_feedback_model: str | None = None
    # Global Gemini fallback, e.g. GEMINI_MODEL=gemini-2.5-flash
    gemini_model: str | None = None
    methodology_rag_top_k: int = 5

    @property
    def video_feedback_model_resolved(self) -> str:
        return (
            self.video_feedback_model
            or self.gemini_model
            or "gemini-2.5-flash"
        )

    @property
    def storage_root(self) -> Path:
        return Path(self.video_storage_dir)

    @property
    def extension_set(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_video_extensions.split(",") if e.strip()}


video_settings = VideoAnalysisSettings()
