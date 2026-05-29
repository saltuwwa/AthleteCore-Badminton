"""Semantic turn router — meaning-based classification (mocked LLM)."""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.graph.semantic_router import (
    MemoryAction,
    SemanticTurnDecision,
    TurnIntent,
    fallback_semantic_route,
    route_user_turn,
)
from app.graph.turn_safety import evaluate_turn_safety
from app.memory.past_event_guard import PastEventResolution, PastEventRetrievalTrace


def _router_json(**fields) -> str:
    base = {
        "turn_intent": "GENERAL_CHAT",
        "event_type": "none",
        "event_date": None,
        "date_confidence": 0.0,
        "has_inline_facts": False,
        "inline_facts_summary": "",
        "health_signal": False,
        "memory_action": "none",
        "recommended_agent": "direct",
        "reason": "test",
    }
    base.update(fields)
    return json.dumps(base, ensure_ascii=False)


@pytest.mark.asyncio
async def test_new_event_log_with_inline_facts():
    msg = (
        "8 февраля была тренировка: бег 5 км, многоваланка, "
        "я выиграла игровую и подвернула голеностоп"
    )
    raw = _router_json(
        turn_intent="NEW_EVENT_LOG",
        event_type="training",
        event_date="2026-02-08",
        date_confidence=0.9,
        has_inline_facts=True,
        inline_facts_summary="бег 5 км, многоваланка, подвернула голеностоп",
        health_signal=True,
        memory_action="write",
        recommended_agent="health_coach",
    )
    with patch("app.graph.semantic_router.acompletion", new_callable=AsyncMock, return_value=raw):
        decision = await route_user_turn(msg, reference=date(2026, 5, 29))

    assert decision.turn_intent == TurnIntent.NEW_EVENT_LOG
    assert decision.has_inline_facts is True
    assert decision.memory_action == MemoryAction.WRITE
    safety = evaluate_turn_safety(decision.to_state_dict(), None)
    assert safety.block_llm is False
    assert safety.safety_invariant_applied == "invariant_2_new_event_log"


@pytest.mark.asyncio
async def test_past_event_lookup_without_inline_facts():
    msg = "Разбери мою тренировку 8 февраля"
    raw = _router_json(
        turn_intent="PAST_EVENT_LOOKUP_REQUEST",
        event_type="training",
        event_date="2026-02-08",
        date_confidence=0.85,
        has_inline_facts=False,
        memory_action="read",
        recommended_agent="analyst",
    )
    with patch("app.graph.semantic_router.acompletion", new_callable=AsyncMock, return_value=raw):
        decision = await route_user_turn(msg, reference=date(2026, 5, 29))

    assert decision.turn_intent == TurnIntent.PAST_EVENT_LOOKUP_REQUEST
    assert decision.has_inline_facts is False
    assert decision.memory_action == MemoryAction.READ

    past = PastEventResolution(
        is_past_event_query=True,
        found=False,
        llm_allowed=False,
        retrieval=PastEventRetrievalTrace(blocked_reason="past_event_not_found"),
    )
    safety = evaluate_turn_safety(decision.to_state_dict(), past)
    assert safety.block_llm is True
    assert safety.safety_invariant_applied == "invariant_1_past_not_found"


@pytest.mark.asyncio
async def test_general_chat():
    raw = _router_json(
        turn_intent="GENERAL_CHAT",
        memory_action="none",
        recommended_agent="direct",
    )
    with patch(
        "app.graph.semantic_router.acompletion",
        new_callable=AsyncMock,
        return_value=raw,
    ):
        decision = await route_user_turn("как дела?", reference=date(2026, 5, 29))

    assert decision.turn_intent == TurnIntent.GENERAL_CHAT
    assert decision.memory_action == MemoryAction.NONE
    safety = evaluate_turn_safety(decision.to_state_dict(), None)
    assert safety.block_llm is False
    assert safety.force_comparison_status is None


@pytest.mark.asyncio
async def test_new_match_log_yesterday():
    msg = "Вчера играла с Машей, выиграла 21:15, но устала"
    raw = _router_json(
        turn_intent="NEW_EVENT_LOG",
        event_type="match",
        event_date="2026-05-28",
        date_confidence=0.8,
        has_inline_facts=True,
        inline_facts_summary="выиграла 21:15 против Маши, устала",
        memory_action="write",
        recommended_agent="analyst",
    )
    with patch("app.graph.semantic_router.acompletion", new_callable=AsyncMock, return_value=raw):
        decision = await route_user_turn(msg, reference=date(2026, 5, 29))

    assert decision.turn_intent == TurnIntent.NEW_EVENT_LOG
    assert decision.event_type.value == "match"
    assert decision.has_inline_facts is True
    assert decision.memory_action == MemoryAction.WRITE


@pytest.mark.asyncio
async def test_past_lookup_why_lost():
    msg = "Почему я тогда проиграла?"
    raw = _router_json(
        turn_intent="PAST_EVENT_LOOKUP_REQUEST",
        has_inline_facts=False,
        memory_action="read",
        recommended_agent="analyst",
    )
    with patch("app.graph.semantic_router.acompletion", new_callable=AsyncMock, return_value=raw):
        decision = await route_user_turn(msg, reference=date(2026, 5, 29))

    assert decision.turn_intent == TurnIntent.PAST_EVENT_LOOKUP_REQUEST
    assert decision.has_inline_facts is False
    past = PastEventResolution(
        is_past_event_query=True,
        found=False,
        llm_allowed=False,
        retrieval=PastEventRetrievalTrace(blocked_reason="past_event_not_found"),
    )
    assert evaluate_turn_safety(decision.to_state_dict(), past).block_llm is True


def test_fallback_new_event_log_not_lookup():
    """Fallback only: rich message must not become lookup-only."""
    msg = (
        "8 февраля была тренировка: бег 5 км, многоваланка, "
        "подвернула голеностоп"
    )
    decision = fallback_semantic_route(msg, reference=date(2026, 5, 29))
    assert decision.turn_intent == TurnIntent.NEW_EVENT_LOG
    assert decision.has_inline_facts is True


@pytest.mark.asyncio
async def test_code_override_inline_facts_to_new_event_log():
    """If LLM says lookup but message has facts, code upgrades to NEW_EVENT_LOG."""
    msg = "8 февраля была тренировка: бег 5 км, многоваланка"
    raw = _router_json(
        turn_intent="PAST_EVENT_LOOKUP_REQUEST",
        has_inline_facts=False,
        memory_action="read",
    )
    with patch(
        "app.graph.semantic_router.acompletion",
        new_callable=AsyncMock,
        return_value=raw,
    ):
        decision = await route_user_turn(msg, reference=date(2026, 5, 29))
    assert decision.turn_intent == TurnIntent.NEW_EVENT_LOG
    assert decision.has_inline_facts is True
