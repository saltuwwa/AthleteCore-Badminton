"""Decide whether LTM recall is needed for this turn (before expensive retrieval)."""

from __future__ import annotations

from typing import Any

# Off-topic / transactional — do not load athlete memory bank
_SKIP_MEMORY_MARKERS = (
    "погод",
    "weather",
    "температур",
    "дожд",
    "снег",
    "прогноз",
    "курс доллар",
    "новост",
    "привет",
    "как дела",
    "спасибо",
    "пока",
    "кто такой",
    "что такое",
)

# Calendar CRUD without planning context
_CALENDAR_TX_MARKERS = (
    "перенес",
    "перенест",
    "сдвин",
    "отмен",
    "удали событ",
    "убери событ",
    "измени время",
    "поменяй время",
    "перестав",
    "reschedule",
    "move event",
    "cancel event",
    "delete event",
)

_CALENDAR_PLAN_MARKERS = (
    "составь",
    "спланир",
    "расписание на",
    "план на недел",
    "weekly plan",
    "оптимиз",
    "распредели нагруз",
)

# Strong signals that personal history matters
_MEMORY_MARKERS = (
    "матч",
    "тренир",
    "ошиб",
    "паттерн",
    "снова",
    "повтор",
    "как в прошл",
    "обычно",
    "мои предпочт",
    "моя цель",
    "травм",
    "нагрузк",
    "восстанов",
    "match",
    "training",
    "pattern",
    "again",
    "history",
)


def heuristic_needs_memory(user_input: str, routed_agent: str) -> bool:
    t = user_input.lower().strip()
    if not t:
        return False

    if any(m in t for m in _SKIP_MEMORY_MARKERS):
        return False

    if routed_agent == "scheduler":
        if any(m in t for m in _CALENDAR_PLAN_MARKERS):
            return True
        if any(m in t for m in _CALENDAR_TX_MARKERS):
            return False
        return False

    if any(m in t for m in _MEMORY_MARKERS):
        return True

    if routed_agent == "analyst":
        return True

    if routed_agent == "health_coach":
        return True

    if routed_agent == "direct":
        return False

    return False


def resolve_needs_memory(
    user_input: str,
    routed_agent: str,
    planner_decision: dict[str, Any],
) -> bool:
    """
    Final gate: planner LLM hint + domain heuristics (heuristics can force skip).
    """
    if any(m in user_input.lower() for m in _SKIP_MEMORY_MARKERS):
        return False

    if routed_agent == "scheduler" and any(
        m in user_input.lower() for m in _CALENDAR_TX_MARKERS
    ):
        if not any(m in user_input.lower() for m in _CALENDAR_PLAN_MARKERS):
            return False

    raw = planner_decision.get("needs_memory")
    if raw is not None:
        return bool(raw)

    return heuristic_needs_memory(user_input, routed_agent)
