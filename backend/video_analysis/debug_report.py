"""
Video analysis debug / eval artifacts.

Writes numbered JSON/MD files under backend/reports/video_debug/{video_id}/.
"""

from __future__ import annotations

import json
import re
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEBUG_ROOT = _BACKEND_ROOT / "reports" / "video_debug"

ARTIFACT_FILES = [
    "01_video_metadata.json",
    "02_sampled_frames.json",
    "03_detected_players.json",
    "04_tracking_summary.json",
    "05_segment_filtering.json",
    "06_target_selection.json",
    "07_metrics.json",
    "08_memory_context.json",
    "09_rag_context.json",
    "10_gemini_input.json",
    "11_gemini_feedback.md",
    "12_timing_report.json",
    "13_errors.json",
]


def debug_report_dir(video_id: str) -> Path:
    return DEBUG_ROOT / video_id


def list_debug_reports() -> list[str]:
    if not DEBUG_ROOT.is_dir():
        return []
    return sorted(p.name for p in DEBUG_ROOT.iterdir() if p.is_dir())


class VideoDebugReporter:
    """Collects timings and writes numbered debug artifacts."""

    def __init__(self, video_id: str, *, enabled: bool = True) -> None:
        self.video_id = video_id
        self.enabled = enabled
        self.report_id = video_id
        self.dir = debug_report_dir(video_id)
        self.timings: dict[str, float] = {}
        self.errors: list[dict[str, Any]] = []
        self._step_start: float | None = None
        self._current_step: str | None = None
        self._t0 = time.perf_counter()

    def record_error(
        self,
        step: str,
        message: str,
        *,
        fallback: str | None = None,
        reliable: bool = True,
    ) -> None:
        self.errors.append(
            {
                "step": step,
                "error": message,
                "fallback_used": fallback,
                "analysis_reliable": reliable,
                "at": datetime.now(UTC).isoformat(),
            }
        )

    @contextmanager
    def step(self, name: str) -> Iterator[None]:
        if not self.enabled:
            yield
            return
        self._current_step = name
        self._step_start = time.perf_counter()
        try:
            yield
        except Exception as e:
            self.record_error(name, str(e), reliable=False)
            raise
        finally:
            if self._step_start is not None:
                self.timings[name] = round(time.perf_counter() - self._step_start, 3)
            self._step_start = None
            self._current_step = None

    def write(self, filename: str, data: Any) -> Path | None:
        if not self.enabled:
            return None
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / filename
        if filename.endswith(".md"):
            path.write_text(str(data), encoding="utf-8")
        else:
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        return path

    def finalize(self) -> dict[str, Any]:
        if not self.enabled:
            return {}
        total = round(time.perf_counter() - self._t0, 3)
        timing_report = {
            **self.timings,
            "total_sec": total,
        }
        key_map = {
            "metadata": "metadata_sec",
            "frame_sampling": "frame_sampling_sec",
            "player_detection": "player_detection_sec",
            "tracking": "tracking_sec",
            "segment_filtering": "segment_filtering_sec",
            "metrics_extraction": "metrics_extraction_sec",
            "memory_retrieval": "memory_retrieval_sec",
            "rag_retrieval": "rag_retrieval_sec",
            "gemini_feedback": "gemini_feedback_sec",
            "memory_write": "memory_write_sec",
        }
        labeled = {key_map.get(k, k): v for k, v in self.timings.items()}
        labeled["total_sec"] = total
        self.write("12_timing_report.json", labeled)
        self.write(
            "13_errors.json",
            {
                "errors": self.errors,
                "has_errors": bool(self.errors),
                "analysis_reliable": not any(e.get("analysis_reliable") is False for e in self.errors),
            },
        )
        index = self.build_index()
        self.write("00_debug_index.json", index)
        return index

    def build_index(self) -> dict[str, Any]:
        artifacts = {}
        for name in ARTIFACT_FILES:
            p = self.dir / name
            artifacts[name] = p.is_file()
        timing_path = self.dir / "12_timing_report.json"
        timing: dict[str, Any] = {}
        if timing_path.is_file():
            timing = json.loads(timing_path.read_text(encoding="utf-8"))
        return {
            "video_id": self.video_id,
            "debug_report_id": self.report_id,
            "artifacts": artifacts,
            "timing": timing,
            "errors_count": len(self.errors),
            "generated_at": datetime.now(UTC).isoformat(),
        }


def redact_secrets(obj: Any) -> Any:
    """Deep-redact API keys and tokens from debug payloads."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = k.lower()
            if any(x in lk for x in ("api_key", "token", "secret", "password", "authorization")):
                out[k] = "***REDACTED***"
            else:
                out[k] = redact_secrets(v)
        return out
    if isinstance(obj, list):
        return [redact_secrets(x) for x in obj]
    if isinstance(obj, str):
        s = re.sub(r"sk-[a-zA-Z0-9]{20,}", "***REDACTED***", obj)
        s = re.sub(r"AIza[a-zA-Z0-9_-]{20,}", "***REDACTED***", s)
        return s
    return obj


def load_debug_bundle(video_id: str) -> dict[str, Any]:
    """Load all debug artifacts for API / frontend."""
    base = debug_report_dir(video_id)
    if not base.is_dir():
        return {}
    bundle: dict[str, Any] = {"video_id": video_id, "debug_report_id": video_id}
    for name in ["00_debug_index.json", *ARTIFACT_FILES]:
        path = base / name
        if not path.is_file():
            continue
        key = name.replace(".json", "").replace(".md", "")
        if name.endswith(".md"):
            bundle[key] = path.read_text(encoding="utf-8")
        else:
            bundle[key] = json.loads(path.read_text(encoding="utf-8"))
    return bundle


def save_preview_image(video_id: str, image_bytes: bytes, name: str = "preview_players.jpg") -> str:
    d = debug_report_dir(video_id)
    d.mkdir(parents=True, exist_ok=True)
    path = d / name
    path.write_bytes(image_bytes)
    return str(path.relative_to(_BACKEND_ROOT))
