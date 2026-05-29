"""LLM extraction: user sport facts + optional confirmed assistant analysis."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from openai import AsyncOpenAI

from app.config import Settings

from .confirmation import ConfirmationSignal, detect_explicit_user_confirmation
from .constants import SOURCE_CONFIRMED_ANALYSIS, SOURCE_USER
from .mapping import normalize_candidate

USER_SYSTEM_PROMPT = """You extract durable memories from a professional badminton athlete's USER message only.
The conversation may include an assistant reply in a separate step — you must NOT see it here.
Do NOT invent facts that could have come from a coach/AI analysis.

Return STRICT JSON:
{
  "memories": [
    {
      "type": "fact | preference | opinion | event",
      "key": "semantic.dotted.key (stable id)",
      "value": "short third-person statement grounded in the USER message",
      "confidence": 0.0-1.0,
      "supersedes_same_key": true or false,
      "risk_level": "low | med | high (optional)",
      "importance": 0.0-1.0,
      "event_type": "match_log | training_log | schedule_confirmation (optional)",
      "session_type": "match | training | recovery | health | tournament | note (optional)",
      "event_date": "YYYY-MM-DD or null",
      "event_date_end": "YYYY-MM-DD or null",
      "event_date_phrase": "original phrase e.g. вчера (optional)",
      "facts": {"opponent": "...", "score": "...", "errors": ["..."], "fatigue": "...", "drills": "..."},
      "is_repeated_pattern": true or false,
      "is_user_confirmed": true or false,
      "payload": {}
    }
  ]
}

Rules:
- Extract ONLY sport facts the athlete explicitly said or clearly implied in USER text.
- Ignore small talk, weather, UI commands, questions with no new sport facts.
- Do NOT copy hypothetical coach/analyst conclusions.
- is_user_confirmed=true only for schedule/HITL the athlete accepts in their own words (e.g. "подтверждаю план").
- If nothing worth storing, return {"memories": []}.
"""

CONFIRMED_ASSISTANT_SYSTEM_PROMPT = """The athlete explicitly confirmed they want to save content from the ASSISTANT message.
Extract ONLY facts that appear in the assistant text AND that the athlete's confirmation clearly endorses.

Return STRICT JSON:
{
  "memories": [
    {
      "type": "fact | preference | opinion | event",
      "key": "semantic.dotted.key",
      "value": "short third-person statement — must be traceable to ASSISTANT text",
      "confidence": 0.0-1.0,
      "supersedes_same_key": true or false,
      "risk_level": "low | med | high (optional)",
      "importance": 0.0-1.0,
      "event_type": "match_log | training_log | schedule_confirmation (optional)",
      "session_type": "match | training | recovery | health | tournament | note (optional)",
      "event_date": "YYYY-MM-DD or null",
      "event_date_end": "YYYY-MM-DD or null",
      "facts": {},
      "is_repeated_pattern": false,
      "is_user_confirmed": true,
      "payload": {"confirmed_from": "assistant"}
    }
  ]
}

Rules:
- Do NOT add new analysis, opponents, scores, or errors not present in the assistant message.
- If confirmation is vague or assistant has no durable sport facts, return {"memories": []}.
- Prefer keys like performance.error.pattern, match.latest, training.session.latest when appropriate.
"""


def _format_reference_block(reference_date: date) -> str:
    return (
        f"reference_date (today for this message): {reference_date.isoformat()}\n"
        "Use this to resolve relative dates into event_date when needed."
    )


def user_messages_only(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [m for m in messages if m.get("role") == "user" and (m.get("content") or "").strip()]


def assistant_messages_only(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        m for m in messages if m.get("role") == "assistant" and (m.get("content") or "").strip()
    ]


def latest_assistant_text(messages: list[dict[str, Any]]) -> str:
    parts = [(m.get("content") or "").strip() for m in assistant_messages_only(messages)]
    return parts[-1] if parts else ""


def concat_user_text(messages: list[dict[str, Any]]) -> str:
    return "\n\n".join((m.get("content") or "").strip() for m in user_messages_only(messages))


def build_user_extraction_request(
    user_msgs: list[dict[str, Any]],
    *,
    reference_date: date,
) -> dict[str, str]:
    """Payload for the user-only LLM call (testable, no assistant roles)."""
    return {
        "system": USER_SYSTEM_PROMPT,
        "user": (
            f"{_format_reference_block(reference_date)}\n\n"
            f"USER messages (JSON):\n{json.dumps(user_msgs, ensure_ascii=False)}\n\n"
            "Extract memories from USER content only."
        ),
    }


def _reference_as_date(reference_date: date | datetime | None) -> date:
    ref = reference_date or date.today()
    if isinstance(ref, datetime):
        return ref.date()
    return ref


async def _call_extractor(
    client: AsyncOpenAI,
    settings: Settings,
    *,
    system: str,
    user_content: str,
) -> list[dict[str, Any]]:
    import time

    from app.observability.langfuse_tracing import record_langfuse_generation

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    t0 = time.perf_counter()
    err_msg: str | None = None
    raw = "{}"
    usage_payload: dict[str, Any] | None = None
    try:
        resp = await client.chat.completions.create(
            model=settings.extraction_model,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=messages,
        )
        raw = resp.choices[0].message.content or "{}"
        u = getattr(resp, "usage", None)
        if u is not None:
            usage_payload = {
                "input": getattr(u, "prompt_tokens", None),
                "output": getattr(u, "completion_tokens", None),
                "total": getattr(u, "total_tokens", None),
            }
    except Exception as exc:
        err_msg = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        record_langfuse_generation(
            name="memory_extraction",
            model=settings.extraction_model,
            messages=messages,
            output=raw,
            duration_ms=(time.perf_counter() - t0) * 1000,
            temperature=0.1,
            usage=usage_payload,
            error=err_msg,
            cfg=settings,
        )
    data = json.loads(raw)
    return data.get("memories") or []


def _normalize_items(
    items: list[dict[str, Any]],
    *,
    source: str,
    force_user_confirmed: bool | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in items:
        try:
            normalized = normalize_candidate(m)
            normalized["source"] = source
            if force_user_confirmed is not None:
                normalized["is_user_confirmed"] = force_user_confirmed
            elif source == SOURCE_USER:
                # User path: never mark as confirmed-analysis unless athlete said so in user text
                normalized["is_user_confirmed"] = bool(normalized.get("is_user_confirmed"))
            out.append(normalized)
        except (KeyError, TypeError, ValueError):
            continue
    return out


async def extract_memories_from_user_turn(
    client: AsyncOpenAI,
    settings: Settings,
    messages_for_prompt: list[dict[str, Any]],
    *,
    reference_date: date | datetime | None = None,
) -> list[dict[str, Any]]:
    """Factual sport memory from user role only — assistant text is never sent to the LLM."""
    user_msgs = user_messages_only(messages_for_prompt)
    if not user_msgs:
        return []

    ref = _reference_as_date(reference_date)
    req = build_user_extraction_request(user_msgs, reference_date=ref)
    items = await _call_extractor(
        client, settings, system=req["system"], user_content=req["user"]
    )
    return _normalize_items(items, source=SOURCE_USER)


async def extract_confirmed_assistant_memories(
    client: AsyncOpenAI,
    settings: Settings,
    *,
    assistant_text: str,
    user_confirmation: str,
    reference_date: date | datetime | None = None,
) -> list[dict[str, Any]]:
    """Extract only when the athlete explicitly confirmed assistant content."""
    assistant_text = (assistant_text or "").strip()
    user_confirmation = (user_confirmation or "").strip()
    if not assistant_text or not user_confirmation:
        return []

    ref = _reference_as_date(reference_date)
    user_content = (
        f"{_format_reference_block(ref)}\n\n"
        f"Athlete confirmation (USER):\n{user_confirmation}\n\n"
        f"ASSISTANT message to persist (only facts from here):\n{assistant_text}\n\n"
        "Extract confirmed memories."
    )
    items = await _call_extractor(
        client,
        settings,
        system=CONFIRMED_ASSISTANT_SYSTEM_PROMPT,
        user_content=user_content,
    )
    return _normalize_items(
        items,
        source=SOURCE_CONFIRMED_ANALYSIS,
        force_user_confirmed=True,
    )


def merge_extraction_candidates(
    user_candidates: list[dict[str, Any]],
    confirmed_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """User-stated facts win on key collision."""
    by_key: dict[str, dict[str, Any]] = {c["key"]: c for c in user_candidates}
    for c in confirmed_candidates:
        by_key.setdefault(c["key"], c)
    return list(by_key.values())


async def extract_memories_from_turn(
    client: AsyncOpenAI,
    settings: Settings,
    messages_for_prompt: list[dict[str, Any]],
    *,
    reference_date: date | datetime | None = None,
    confirmation: ConfirmationSignal | None = None,
) -> list[dict[str, Any]]:
    """
    Default: user-only extraction (source=user).
    If the athlete explicitly confirmed assistant output, also extract confirmed_analysis.
    """
    user_candidates = await extract_memories_from_user_turn(
        client,
        settings,
        messages_for_prompt,
        reference_date=reference_date,
    )

    user_text = concat_user_text(messages_for_prompt)
    signal = confirmation or detect_explicit_user_confirmation(user_text)
    if not signal.confirmed:
        return user_candidates

    assistant_text = latest_assistant_text(messages_for_prompt)
    if not assistant_text:
        return user_candidates

    confirmed = await extract_confirmed_assistant_memories(
        client,
        settings,
        assistant_text=assistant_text,
        user_confirmation=user_text,
        reference_date=reference_date,
    )
    return merge_extraction_candidates(user_candidates, confirmed)
