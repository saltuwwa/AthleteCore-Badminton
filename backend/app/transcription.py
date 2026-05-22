"""OpenAI Whisper STT for voice match/training logs."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from openai import APIError, AsyncOpenAI

from app.config import Settings, settings

MAX_AUDIO_BYTES = 25 * 1024 * 1024


async def transcribe_audio_bytes(
    audio_bytes: bytes,
    *,
    filename: str = "recording.webm",
    app_settings: Settings | None = None,
) -> tuple[str, float | None]:
    """
    Transcribe audio via Whisper API.

    Returns (text, duration_sec). duration may be None if not reported.
    """
    cfg = app_settings or settings
    if not cfg.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for Whisper")

    if not audio_bytes:
        raise ValueError("Empty audio payload")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise ValueError("Audio file too large (max 25 MB)")

    suffix = Path(filename).suffix or ".webm"
    client = AsyncOpenAI(api_key=cfg.openai_api_key)

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        with open(tmp_path, "rb") as audio_file:
            result = await client.audio.transcriptions.create(
                model=cfg.whisper_model,
                file=audio_file,
                language=cfg.whisper_language,
                response_format="verbose_json",
            )

        text = (result.text or "").strip()
        duration = getattr(result, "duration", None)
        return text, float(duration) if duration is not None else None
    except APIError:
        raise
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
