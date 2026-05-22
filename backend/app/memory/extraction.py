"""LLM extraction: athlete turn → structured memories (sports-adapted)."""

from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from app.config import Settings

from .mapping import normalize_candidate

SYSTEM_PROMPT = """You extract durable memories from a professional badminton athlete's conversation turn.

Return STRICT JSON:
{
  "memories": [
    {
      "type": "fact | preference | opinion | event",
      "key": "semantic.dotted.key (stable id)",
      "value": "short third-person statement for the memory bank",
      "confidence": 0.0-1.0,
      "supersedes_same_key": true or false,
      "risk_level": "low | med | high (optional)",
      "importance": 0.0-1.0,
      "event_type": "match_log | training_log | schedule_confirmation (optional)",
      "is_repeated_pattern": true or false,
      "is_user_confirmed": true or false,
      "payload": {}
    }
  ]
}

Key conventions (use consistently):
- training.preference.time — preferred training slot
- health.injury.current — injury / limitation
- goal.season — competition goal
- recovery.preference — recovery habits
- match.latest — notable match outcome / tactics
- performance.error.pattern — recurring tactical/physical error
- training.session.latest — training log summary
- schedule.confirmation — user accepted/rejected AI schedule change
- agent.response_style — how the athlete wants answers (procedural)
- hitl.confirmation_strictness — how strict plan confirmation should be

Rules:
- Extract facts, preferences, opinions, match/training events, HITL decisions.
- Reuse the SAME key when updating a topic; set supersedes_same_key=true on corrections.
- Mark performance.error.pattern with risk_level med/high when errors repeat or are serious.
- Set is_user_confirmed=true when the athlete explicitly confirms or rejects an AI plan.
- Set is_repeated_pattern=true when the user mentions the same error/issue again.
- Ignore small talk with no training value.
- If nothing worth storing, return {"memories": []}.
"""


async def extract_memories_from_turn(
    client: AsyncOpenAI,
    settings: Settings,
    messages_for_prompt: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    user_blob = json.dumps(messages_for_prompt, ensure_ascii=False)
    resp = await client.chat.completions.create(
        model=settings.extraction_model,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Conversation fragment (JSON):\n{user_blob}\n\nExtract memories.",
            },
        ],
    )
    raw = resp.choices[0].message.content or "{}"
    data = json.loads(raw)
    items = data.get("memories") or []
    out: list[dict[str, Any]] = []
    for m in items:
        try:
            out.append(normalize_candidate(m))
        except (KeyError, TypeError, ValueError):
            continue
    return out
