from __future__ import annotations

import json
import re
from typing import Any

from app.config import Settings, settings


def _litellm_model(model: str, cfg: Settings) -> tuple[str, str | None]:
    """Return (litellm_model_id, api_key)."""
    if model.startswith("claude") or model.startswith("anthropic/"):
        mid = model if model.startswith("anthropic/") else f"anthropic/{model}"
        return mid, cfg.anthropic_api_key
    return model, cfg.openai_api_key


async def acompletion(
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
    app_settings: Settings | None = None,
) -> str:
    """LiteLLM gateway with OpenAI / Anthropic keys from settings."""
    cfg = app_settings or settings
    import litellm

    litellm_model, api_key = _litellm_model(model, cfg)
    if not api_key:
        raise RuntimeError(f"No API key configured for model {model}")

    resp = await litellm.acompletion(
        model=litellm_model,
        messages=messages,
        temperature=temperature,
        api_key=api_key,
    )
    return (resp.choices[0].message.content or "").strip()


def resolve_analyst_model(cfg: Settings) -> str:
    if cfg.anthropic_api_key:
        return cfg.analyst_model
    return "gpt-4o-mini"


def parse_planner_json(raw: str) -> dict[str, Any]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


def heuristic_route(user_input: str) -> dict[str, Any]:
    """Fallback routing without LLM."""
    from app.graph.interaction import (
        detect_emotional_tone,
        is_analysis_consent,
        wants_explicit_debrief,
    )

    t = user_input.lower()
    tone = detect_emotional_tone(user_input)
    if wants_explicit_debrief(user_input):
        return {
            "agents": ["analyst"],
            "reason": "heuristic-explicit-debrief",
            "needs_confirmation": False,
            "interaction_mode": "full_analysis",
            "needs_memory": True,
        }
    if is_analysis_consent(user_input) and len(t) < 80:
        return {
            "agents": ["analyst"],
            "reason": "heuristic-consent-analysis",
            "needs_confirmation": False,
            "interaction_mode": "full_analysis",
            "needs_memory": True,
        }
    if any(
        w in t
        for w in (
            "восстанов",
            "сон",
            "питани",
            "травм",
            "устал",
            "нагрузк",
            "recovery",
            "health",
        )
    ) and not any(w in t for w in ("проигр", "ошиб", "матч", "поражен", "провал")):
        return {
            "agents": ["health_coach"],
            "reason": "heuristic-health",
            "needs_confirmation": False,
            "interaction_mode": "neutral",
            "needs_memory": True,
        }
    if tone == "distressed":
        return {
            "agents": ["analyst"],
            "reason": "heuristic-distress-support",
            "needs_confirmation": False,
            "interaction_mode": "support_first",
            "needs_memory": True,
        }
    if tone == "positive":
        return {
            "agents": ["analyst"],
            "reason": "heuristic-celebrate",
            "needs_confirmation": False,
            "interaction_mode": "celebrate_first",
            "needs_memory": True,
        }
    if any(
        w in t
        for w in (
            "расписан",
            "календар",
            "недельн",
            "на неделю",
            "schedule",
            "план трен",
        )
    ):
        return {"agents": ["scheduler"], "reason": "heuristic-schedule", "needs_confirmation": True}
    if any(
        w in t
        for w in (
            "матч",
            "тренир",
            "ошиб",
            "подач",
            "раунд",
            "сет ",
            "match",
            "training",
            "error",
        )
    ):
        return {"agents": ["analyst"], "reason": "heuristic-analyst", "needs_confirmation": False}
    return {"agents": ["direct"], "reason": "heuristic-direct", "needs_confirmation": False}


def extract_analysis_json(text: str) -> dict[str, Any] | None:
    match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
    blob = match.group(1) if match else None
    if not blob:
        match = re.search(r'\{[\s\S]*"errors"[\s\S]*\}', text)
        blob = match.group() if match else None
    if not blob:
        return None
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return None


def strip_analysis_json_from_text(text: str) -> str:
    """Remove analyst JSON block from user-visible message (structured data is in `analysis`)."""
    if not text:
        return text
    cleaned = re.sub(r"```json\s*[\s\S]*?\s*```", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r'\{[\s\S]*"errors"[\s\S]*\}', "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
