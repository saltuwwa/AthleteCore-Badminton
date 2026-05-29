"""Analyst development trace + past-event LLM invariant."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.graph.analyst_trace import (
    AnalystTrace,
    assert_past_event_llm_invariant,
    trace_from_past_event_resolution,
)
from app.memory.models import Base
from app.memory.past_event_guard import resolve_past_event


@pytest.mark.asyncio
async def test_past_event_empty_db_trace_invariant():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        resolution = await resolve_past_event(
            session,
            user_input="Разбери мою последнюю тренировку",
            user_id="u1",
            session_id="main",
            reference=date(2026, 5, 29),
        )
    await engine.dispose()

    assert resolution.is_past_event_request
    assert not resolution.found
    assert not resolution.llm_allowed
    assert resolution.retrieval.retrieved_memory_items == []

    trace = trace_from_past_event_resolution(
        user_input="Разбери мою последнюю тренировку",
        state={"routed_agent": "analyst", "interaction_mode": "full_analysis"},
        past=resolution,
    )
    assert_past_event_llm_invariant(trace)
    assert trace.llm_called is False
    assert trace.retrieved_memory_items_count == 0
    assert trace.is_past_event_request is True

    payload = trace.to_dict()
    assert payload["user_message"]
    assert "past_event" in str(payload["detected_intent"])
    assert payload["llm_called"] is False
    assert payload["retrieved_memory_items"]["count"] == 0
    assert payload["blocked_reason"] == "past_event_not_found"


def test_analyst_trace_required_fields():
    t = AnalystTrace(
        user_message="test",
        detected_intent={"routed_agent": "analyst"},
        is_past_event_request=True,
        memory_query="past_event:last_training",
        confidence_score=0.0,
        llm_called=False,
        blocked_reason="past_event_not_found",
    )
    d = t.to_dict()
    for key in (
        "user_message",
        "detected_intent",
        "is_past_event_request",
        "memory_query",
        "retrieved_memory_items",
        "confidence_score",
        "llm_called",
        "structured_retrieval_used",
        "structured_function_called",
        "semantic_fallback_used",
        "blocked_reason",
        "inline_facts_in_message",
    ):
        assert key in d
    assert d["retrieved_memory_items"]["count"] == 0


def test_hard_invariant_regression_llm_called_true_is_forbidden():
    """
    Regression: if past_event + no memory + no inline facts, llm_called must not stay true.
    """
    trace = AnalystTrace(
        is_past_event_request=True,
        inline_facts_in_message=False,
        llm_called=True,
    )
    with pytest.raises(AssertionError, match="Analyst trace invariant violated"):
        assert_past_event_llm_invariant(trace)

    trace.llm_called = True
    trace.apply_past_event_invariant()
    assert trace.llm_called is False
    assert trace.blocked_reason


def test_hard_invariant_passes_when_inline_facts_present():
    trace = AnalystTrace(
        is_past_event_request=True,
        inline_facts_in_message=True,
        llm_called=True,
    )
    assert_past_event_llm_invariant(trace)
    assert trace.llm_called is True


def test_hard_invariant_passes_when_memory_retrieved():
    from app.memory.retrieval_trace import RetrievedMemoryTraceItem

    trace = AnalystTrace(
        is_past_event_request=True,
        inline_facts_in_message=False,
        llm_called=True,
        retrieved_memory_items=[
            RetrievedMemoryTraceItem(
                memory_id="1",
                event_date="2026-05-28",
                match_reason="structured:last_training:dated",
            )
        ],
    )
    assert_past_event_llm_invariant(trace)
    assert trace.llm_called is True
