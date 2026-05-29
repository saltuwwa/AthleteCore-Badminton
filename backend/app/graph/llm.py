from __future__ import annotations

import json
import re
import time
from contextlib import nullcontext
from typing import Any

from app.config import Settings, settings
from app.graph.latency_trace import current_latency_trace, stage_span


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
    latency_name: str | None = None,
    latency_stage: str | None = None,
) -> str:
    """LiteLLM gateway with OpenAI / Anthropic keys from settings."""
    cfg = app_settings or settings
    import litellm

    litellm_model, api_key = _litellm_model(model, cfg)
    if not api_key:
        raise RuntimeError(f"No API key configured for model {model}")

    from app.observability.langfuse_tracing import record_langfuse_generation

    prompt_chars = sum(len(str(m.get("content") or "")) for m in messages)
    stage = latency_stage
    if stage is None and latency_name:
        stage = "semantic_router" if latency_name == "semantic_router" else "agent_llm"

    gen_name = latency_name or stage or "llm"
    ctx = stage_span(stage) if stage else nullcontext()
    t0 = time.perf_counter()
    duration_ms = 0.0
    content = ""
    usage_payload: dict[str, Any] | None = None
    err_msg: str | None = None
    with ctx:
        try:
            resp = await litellm.acompletion(
                model=litellm_model,
                messages=messages,
                temperature=temperature,
                api_key=api_key,
            )
            content = (resp.choices[0].message.content or "").strip()
            u = getattr(resp, "usage", None)
            if u is not None:
                usage_payload = {
                    "input": getattr(u, "prompt_tokens", None) or (u.get("prompt_tokens") if isinstance(u, dict) else None),
                    "output": getattr(u, "completion_tokens", None) or (u.get("completion_tokens") if isinstance(u, dict) else None),
                    "total": getattr(u, "total_tokens", None) or (u.get("total_tokens") if isinstance(u, dict) else None),
                }
        except Exception as exc:
            err_msg = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            duration_ms = (time.perf_counter() - t0) * 1000
            record_langfuse_generation(
                name=gen_name,
                model=model,
                messages=messages,
                output=content,
                duration_ms=duration_ms,
                temperature=temperature,
                usage=usage_payload,
                error=err_msg,
                cfg=cfg,
            )

    trace = current_latency_trace()
    if trace and latency_name:
        trace.record_llm_call(
            name=latency_name,
            model=model,
            duration_ms=duration_ms,
            prompt_chars=prompt_chars,
            completion_chars=len(content),
        )
    return content


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
        match = re.search(
            r'\{[\s\S]*"(?:errors|summary)"[\s\S]*\}', text
        )
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
    cleaned = re.sub(
        r'\{[\s\S]*"(?:errors|summary)"[\s\S]*\}', "", cleaned
    )
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
