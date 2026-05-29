"""In-flight memory writes — ground immediate follow-up before LTM commit."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date

from app.memory.past_event_guard import PastEventIntent, format_inline_message_grounding

_lock = asyncio.Lock()
_pending: dict[str, PendingWrite] = {}


@dataclass
class PendingWrite:
    user_message: str
    assistant_message: str
    event_date: str | None
    inline_facts_summary: str
    event_type: str | None


def _key(user_id: str, session_id: str) -> str:
    return f"{user_id}:{session_id}"


async def register_pending(
    *,
    user_id: str,
    session_id: str,
    user_message: str,
    assistant_message: str,
    event_date: str | None = None,
    inline_facts_summary: str = "",
    event_type: str | None = None,
) -> None:
    async with _lock:
        _pending[_key(user_id, session_id)] = PendingWrite(
            user_message=user_message,
            assistant_message=assistant_message[:4000],
            event_date=event_date,
            inline_facts_summary=inline_facts_summary or user_message[:200],
            event_type=event_type,
        )


async def clear_pending(*, user_id: str, session_id: str) -> None:
    async with _lock:
        _pending.pop(_key(user_id, session_id), None)


def get_pending(user_id: str | None, session_id: str) -> PendingWrite | None:
    if not user_id:
        return None
    return _pending.get(_key(user_id, session_id))


def pending_grounding_for_lookup(
    user_id: str | None,
    session_id: str,
    intent: PastEventIntent,
    *,
    user_input: str = "",
) -> str | None:
    """If DB has not caught up yet, allow grounding from the just-logged turn."""
    pw = get_pending(user_id, session_id)
    if pw is None:
        return None

    if intent.kind in ("last_training", "analyze_past", "progress_review"):
        if intent.event_focus in (None, "training", "any"):
            label = pw.inline_facts_summary[:120] or "тренировка из недавнего сообщения"
            return format_inline_message_grounding(
                pw.user_message, reference_label=label
            )

    if intent.target_date and pw.event_date:
        try:
            target = intent.target_date
            pending_d = date.fromisoformat(pw.event_date)
            if target == pending_d:
                label = f"тренировка ({pw.event_date})"
                return format_inline_message_grounding(pw.user_message, reference_label=label)
        except ValueError:
            pass

    if intent.kind == "date" and intent.day and intent.month and pw.event_date:
        try:
            pending_d = date.fromisoformat(pw.event_date)
            if pending_d.day == intent.day and pending_d.month == intent.month:
                return format_inline_message_grounding(
                    pw.user_message,
                    reference_label=f"событие {intent.day:02d}.{intent.month:02d}",
                )
        except ValueError:
            pass

    t = (user_input or "").lower()
    if any(
        p in t
        for p in (
            "последн",
            "только что",
            "только что добав",
            "которую только",
            "которую я только",
        )
    ):
        label = pw.inline_facts_summary[:120] or "недавнее событие"
        return format_inline_message_grounding(pw.user_message, reference_label=label)

    return None
