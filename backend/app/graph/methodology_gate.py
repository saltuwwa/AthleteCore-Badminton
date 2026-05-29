"""When to call methodology RAG for analyst prompts."""

from __future__ import annotations

from app.graph.semantic_router import TurnIntent

_METHODOLOGY_ASK_MARKERS = (
    "упражнен",
    "дрилл",
    "drill",
    "методик",
    "техник",
    "footwork",
    "работа ног",
    "как делать",
    "как улучшить",
    "как тренировать",
    "план трен",
    "программ трен",
    "разминк",
    "заминк",
    "рекомендуй",
    "посоветуй",
    "что делать чтобы",
    "как восстанов",
    "восстановлен",
    "перед турнир",
    "подготовк",
)

_DEBRIEF_ONLY_MARKERS = (
    "разбери",
    "разобрать",
    "проанализ",
    "что было",
    "как прошла",
    "как прошёл",
    "как прошло",
    "итог",
    "результат",
    "оцени трениров",
    "оцени матч",
)


def needs_methodology_rag(
    user_input: str,
    *,
    turn_intent: str | None,
    past_event_found: bool = False,
) -> tuple[bool, str | None]:
    """
    Returns (use_rag, skip_reason).
    skip_reason is set when RAG is skipped (for latency trace).
    """
    t = (user_input or "").strip().lower()
    intent = turn_intent or ""

    has_methodology_ask = any(m in t for m in _METHODOLOGY_ASK_MARKERS)

    if intent in (TurnIntent.ADVICE_REQUEST.value, TurnIntent.HEALTH_CHECK.value):
        if has_methodology_ask or "восстанов" in t or "совет" in t:
            return True, None
        if intent == TurnIntent.HEALTH_CHECK.value:
            return True, None

    if intent == TurnIntent.CALENDAR_ACTION.value:
        return False, "calendar_action"

    if intent == TurnIntent.GENERAL_CHAT.value:
        return False, "general_chat"

    if intent == TurnIntent.PAST_EVENT_LOOKUP_REQUEST.value and past_event_found:
        if has_methodology_ask:
            return True, None
        return False, "past_event_grounded_recap"

    if intent == TurnIntent.NEW_EVENT_LOG.value:
        if has_methodology_ask:
            return True, None
        return False, "new_event_log_no_methodology_ask"

    if has_methodology_ask:
        return True, None

    if intent == TurnIntent.CURRENT_SESSION_ANALYSIS.value:
        return True, None

    return False, "not_advice_or_drill_request"
