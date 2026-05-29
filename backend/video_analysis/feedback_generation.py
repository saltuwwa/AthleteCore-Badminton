from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException

from video_analysis.config import video_settings
from video_analysis.schemas import CoachingFeedback, VideoMetricsSummary

try:
    from app.memory.video_memory_service import VideoMemoryContext
except ImportError:
    VideoMemoryContext = None  # type: ignore[misc, assignment]

COACHING_DISCLAIMER = (
    "Coaching feedback is AI-generated from approximate pose-based metrics, "
    "past video analyses, and methodology snippets. "
    "It is not a substitute for a human coach or medical advice."
)


def _build_rag_query(metrics: VideoMetricsSummary, memory_ctx: Any | None) -> str:
    parts = [
        "badminton coaching",
        metrics.match_type,
        "movement footwork recovery fatigue attack defense",
    ]
    if metrics.singles:
        parts.append(
            f"speed trend drop {metrics.singles.speed_drop_percent} "
            f"attack ratio {metrics.singles.attack_like_ratio}"
        )
    if metrics.doubles:
        parts.append("doubles partner spacing rotation")
    if memory_ctx and memory_ctx.repeated_patterns:
        parts.append("recurring fatigue speed drop pattern")
    return " ".join(str(p) for p in parts if p)


def fetch_methodology_context(
    metrics: VideoMetricsSummary,
    memory_ctx: Any | None = None,
    *,
    return_hits: bool = False,
) -> tuple[str, list[str]] | tuple[str, list[str], list[dict[str, Any]]]:
    try:
        from app.mcp_tools.methodology import format_methodology_context, search_sports_methodology
    except ImportError:
        if return_hits:
            return "", [], []
        return "", []

    query = _build_rag_query(metrics, memory_ctx)
    hits = search_sports_methodology(query, top_k=video_settings.methodology_rag_top_k)
    if not hits:
        if return_hits:
            return "", [], []
        return "", []
    sources = sorted({h.get("source", "") for h in hits if h.get("source")})
    ctx = format_methodology_context(hits)
    if return_hits:
        chunk_debug = [
            {
                "source": h.get("source", ""),
                "title": h.get("title") or h.get("metadata", {}).get("title", ""),
                "score": h.get("score"),
                "why_retrieved": f"query match: {query[:120]}",
                "excerpt_preview": (h.get("text") or h.get("content") or "")[:200],
            }
            for h in hits
        ]
        return ctx, sources, chunk_debug
    return ctx, sources


def _metrics_to_prompt(metrics: VideoMetricsSummary) -> str:
    return json.dumps(metrics.model_dump(mode="json"), ensure_ascii=False, indent=2)


def build_gemini_payload(
    metrics: VideoMetricsSummary,
    memory_ctx: VideoMemoryContext | None = None,
    *,
    methodology_ctx: str = "",
    methodology_sources: list[str] | None = None,
) -> dict[str, Any]:
    """Exact structured payload sent to Gemini (no raw video, no secrets)."""
    segment_summary = None
    if metrics.segment_filter:
        segment_summary = {
            "valid_gameplay_ratio": metrics.segment_filter.valid_gameplay_ratio,
            "valid_segments": [s.model_dump() for s in metrics.segment_filter.valid_segments],
            "ignored_segments": [s.model_dump() for s in metrics.segment_filter.ignored_segments],
            "warning": metrics.segment_filter.warning,
        }

    user_parts = [
        "## Current video metrics JSON (pose-based, approximate)",
        _metrics_to_prompt(metrics),
    ]
    memory_block = ""
    if memory_ctx is not None:
        memory_block = memory_ctx.format_for_prompt()
        if memory_block.strip():
            user_parts.append("## Athlete video memory (LTM)")
            user_parts.append(memory_block)
    if methodology_ctx:
        user_parts.append("## Methodology context (RAG from coaching books)")
        user_parts.append(methodology_ctx)

    return {
        "model": video_settings.video_feedback_model_resolved,
        "system_instruction_summary": (
            "AthleteCore badminton coaching assistant; Russian output; JSON only; "
            "no raw video; cautious approximate pose metrics language."
        ),
        "target_athlete": {
            "match_type": metrics.match_type,
            "target_track_ids": metrics.target_track_ids,
        },
        "valid_segments_summary": segment_summary,
        "metrics_json": metrics.model_dump(mode="json"),
        "memory_context_text": memory_block or None,
        "rag_context_text": methodology_ctx or None,
        "rag_sources": methodology_sources or [],
        "user_message": "\n\n".join(user_parts),
        "generation_config": {"temperature": 0.35, "response_mime_type": "application/json"},
    }


def _parse_gemini_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def generate_coaching_feedback(
    metrics: VideoMetricsSummary,
    memory_ctx: VideoMemoryContext | None = None,
    *,
    return_debug: bool = False,
) -> CoachingFeedback | tuple[CoachingFeedback, dict[str, Any]]:
    api_key = video_settings.google_api_key
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="GOOGLE_API_KEY not configured for video coaching feedback",
        )

    rag_hits_debug: list[dict[str, Any]] = []
    if return_debug:
        methodology_ctx, sources, rag_hits_debug = fetch_methodology_context(  # type: ignore[misc]
            metrics, memory_ctx, return_hits=True
        )
    else:
        methodology_ctx, sources = fetch_methodology_context(metrics, memory_ctx)
    gemini_payload = build_gemini_payload(
        metrics, memory_ctx, methodology_ctx=methodology_ctx, methodology_sources=sources
    )

    system = """You are AthleteCore badminton coaching assistant.
You receive structured pose-tracking metrics JSON for the CURRENT video (not raw video).
You may also receive past video_analysis memories, repeated patterns, improvements, and athlete baseline.

Write coaching feedback in Russian.

Rules:
- Use cautious language: "possible", "likely", "estimated from pose landmarks", "based on visible movement".
- Do NOT claim exact biomechanics, joint angles, or shuttle speed.
- Do NOT diagnose injury.
- Compare with past videos when context is provided: repeated mistake, improvement, regression.
- Give 3-5 practical coaching recommendations and exactly one drill for next training.
- Return STRICT JSON only with keys:
  short_summary,
  key_timeline_moments (array of strings),
  speed_trend,
  attack_vs_defense_analysis,
  possible_fatigue_moment (string or null),
  coaching_recommendations (array 3-5 strings),
  drill_for_next_training (string),
  repeated_mistakes (array of strings — from cross-video patterns),
  improvements_noted (array of strings),
  regressions_noted (array of strings),
  next_training_focus (string)
"""

    user_blob = gemini_payload["user_message"]

    try:
        import google.generativeai as genai  # type: ignore[import-untyped]
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail="google-generativeai required: pip install google-generativeai",
        ) from e

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        video_settings.video_feedback_model_resolved,
        system_instruction=system,
    )
    response = model.generate_content(
        user_blob,
        generation_config={"temperature": 0.35, "response_mime_type": "application/json"},
    )
    raw = (response.text or "").strip()
    if not raw:
        raise HTTPException(status_code=502, detail="Empty response from Gemini")

    try:
        data = _parse_gemini_json(raw)
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status_code=502, detail=f"Gemini JSON parse error: {e}") from e

    recs = data.get("coaching_recommendations") or []
    if isinstance(recs, str):
        recs = [recs]
    if len(recs) < 3:
        recs = list(recs) + [
            "Сверьте ощущения на корте с видимой динамикой — метрики приблизительные.",
            "Добавьте короткий блок восстановления, если спад скорости совпал с усталостью.",
        ]
        recs = recs[:5]

    def _str_list(key: str) -> list[str]:
        v = data.get(key) or []
        if isinstance(v, str):
            return [v]
        return [str(x) for x in v][:6]

    feedback = CoachingFeedback(
        short_summary=str(data.get("short_summary", "Краткий разбор на основе pose-метрик.")),
        key_timeline_moments=[str(x) for x in (data.get("key_timeline_moments") or [])][:8],
        speed_trend=str(data.get("speed_trend", "Тренд скорости оценён по видимому движению.")),
        attack_vs_defense_analysis=str(
            data.get(
                "attack_vs_defense_analysis",
                "Соотношение атакующих/оборонительных фаз приблизительное.",
            )
        ),
        possible_fatigue_moment=data.get("possible_fatigue_moment"),
        coaching_recommendations=[str(r) for r in recs[:5]],
        drill_for_next_training=str(
            data.get(
                "drill_for_next_training",
                "20 мин: работа ног с акцентом на split step и возврат в базу.",
            )
        ),
        repeated_mistakes=_str_list("repeated_mistakes"),
        improvements_noted=_str_list("improvements_noted"),
        regressions_noted=_str_list("regressions_noted"),
        next_training_focus=data.get("next_training_focus"),
        methodology_sources_used=sources,
        disclaimer=COACHING_DISCLAIMER,
    )
    if return_debug:
        debug_info = {
            "gemini_input": gemini_payload,
            "gemini_raw_response": raw,
            "parsed_feedback": feedback.model_dump(mode="json"),
            "methodology_sources": sources,
            "rag_hits": rag_hits_debug,
        }
        return feedback, debug_info
    return feedback
