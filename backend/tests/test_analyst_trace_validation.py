"""
Validation pass: analyst_trace + no-memory/no-LLM invariant (5 product scenarios).

Each test documents request → analyst_trace → user-visible response → pass/fail.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.graph.analyst_trace import (
    AnalystTrace,
    assert_past_event_llm_invariant,
    trace_from_past_event_resolution,
)
from app.graph.nodes import analyst_node
from app.memory.models import Base, ExtractedMemoryType, Memory, MemoryLayer, Turn
from app.memory.past_event_guard import resolve_past_event

USER = "trace-validation"
SESSION = "main"
REF = date(2026, 5, 29)

MOCK_ANALYSIS_JSON = (
    '{"summary":"ok","issues":[{"title":"footwork","severity":"MED"}]}'
)


@dataclass
class ScenarioResult:
    name: str
    request: str
    analyst_trace: dict[str, Any]
    response_text: str
    analysis: Any
    llm_called: bool
    passed: bool
    notes: str = ""


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def dev_settings(monkeypatch):
    cfg = Settings(development_mode=True, openai_api_key="test-key")
    monkeypatch.setattr("app.graph.nodes.settings", cfg)
    return cfg


async def _seed_training(
    session: AsyncSession,
    *,
    event_date: date,
    value: str = "Силовая 90 мин RPE 7",
) -> Memory:
    turn = Turn(
        session_id=SESSION,
        user_id=USER,
        messages=[{"role": "user", "content": value}],
        turn_timestamp=datetime.now(timezone.utc),
    )
    session.add(turn)
    await session.flush()
    mem = Memory(
        user_id=USER,
        source_session=SESSION,
        source_turn_id=turn.id,
        key="training.session",
        value=value,
        memory_type=ExtractedMemoryType.event,
        memory_layer=MemoryLayer.episodic,
        event_type="training_log",
        session_type="training",
        event_date=event_date,
        confidence=0.9,
        importance=0.8,
        active=True,
    )
    session.add(mem)
    await session.flush()
    return mem


async def _seed_match(
    session: AsyncSession,
    *,
    event_date: date,
    value: str = "Match log",
) -> Memory:
    turn = Turn(
        session_id=SESSION,
        user_id=USER,
        messages=[{"role": "user", "content": value}],
        turn_timestamp=datetime.now(timezone.utc),
    )
    session.add(turn)
    await session.flush()
    mem = Memory(
        user_id=USER,
        source_session=SESSION,
        source_turn_id=turn.id,
        key="match.session",
        value=value,
        memory_type=ExtractedMemoryType.event,
        memory_layer=MemoryLayer.episodic,
        event_type="match_log",
        session_type="match",
        event_date=event_date,
        confidence=0.9,
        importance=0.8,
        active=True,
    )
    session.add(mem)
    await session.flush()
    return mem


def _turn_decision_for_input(user_input: str) -> dict[str, Any]:
    from app.memory.past_event_guard import user_provided_facts_in_message
    from app.memory.past_event_intent import detect_past_event_signals

    if detect_past_event_signals(user_input):
        if user_provided_facts_in_message(user_input):
            return {
                "turn_intent": "NEW_EVENT_LOG",
                "has_inline_facts": True,
                "memory_action": "write",
            }
        return {
            "turn_intent": "PAST_EVENT_LOOKUP_REQUEST",
            "has_inline_facts": False,
            "memory_action": "read",
        }
    if user_provided_facts_in_message(user_input):
        return {
            "turn_intent": "NEW_EVENT_LOG",
            "has_inline_facts": True,
            "memory_action": "write",
        }
    return {
        "turn_intent": "CURRENT_SESSION_ANALYSIS",
        "has_inline_facts": False,
        "memory_action": "read",
    }


async def _run_analyst(
    db: AsyncSession,
    user_input: str,
    *,
    dev_settings: Settings,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    state = {
        "user_input": user_input,
        "user_id": USER,
        "session_id": SESSION,
        "interaction_mode": "full_analysis",
        "memory_context": "",
        "memory_citations": [],
        "routed_agent": "analyst",
        "turn_decision": _turn_decision_for_input(user_input),
    }
    with (
        patch(
            "app.graph.nodes.acompletion",
            new_callable=AsyncMock,
            return_value=MOCK_ANALYSIS_JSON,
        ),
        patch("app.memory.embeddings.embed_query", new_callable=AsyncMock, return_value=None),
    ):
        out = await analyst_node(
            state,
            {"configurable": {"db_session": db}},
        )
    analyst = out["agent_outputs"][0]
    trace = out.get("analyst_trace") or {}
    return out, trace, analyst


def _no_fake_analysis_cards(content: str, analysis: Any) -> bool:
    lower = (content or "").lower()
    if analysis is not None:
        return False
    for marker in ("high", "med", "усталост", "тактик", "психолог"):
        if marker in lower:
            return False
    return True


def _trace_items_not_from_ltm(trace: dict[str, Any]) -> bool:
    for item in trace.get("retrieved_memory_items", {}).get("items", []):
        reason = (item.get("match_reason") or "").lower()
        if reason.startswith("structured:") or reason == "semantic_fallback":
            return False
    return True


# --- Scenario 1 ---


@pytest.mark.asyncio
async def test_scenario_1_empty_memory_past_training(db_session, dev_settings):
    request = "Разбери мою последнюю тренировку"
    resolution = await resolve_past_event(
        db_session,
        user_input=request,
        user_id=USER,
        session_id=SESSION,
        reference=REF,
        app_settings=Settings(openai_api_key=""),
    )
    out, trace, analyst = await _run_analyst(db_session, request, dev_settings=dev_settings)

    passed = (
        trace.get("is_past_event_request") is True
        and trace.get("structured_retrieval_used") is True
        and trace.get("retrieved_memory_items", {}).get("count") == 0
        and trace.get("inline_facts_in_message") is False
        and trace.get("llm_called") is False
        and trace.get("blocked_reason") == "past_event_not_found"
        and analyst.get("analysis") is None
        and _no_fake_analysis_cards(analyst.get("content") or "", analyst.get("analysis"))
        and (
            "последнюю тренировку" in (analyst.get("content") or "").lower()
            or "не нашёл" in (analyst.get("content") or "").lower()
        )
        and out.get("llm_called") is False
    )
    assert_past_event_llm_invariant(
        trace_from_past_event_resolution(
            user_input=request,
            state={"routed_agent": "analyst"},
            past=resolution,
        )
    )

    result = ScenarioResult(
        name="1_empty_memory_past_training",
        request=request,
        analyst_trace=trace,
        response_text=analyst.get("content") or "",
        analysis=analyst.get("analysis"),
        llm_called=bool(trace.get("llm_called")),
        passed=passed,
    )
    assert result.passed, json.dumps(result.__dict__, ensure_ascii=False, indent=2, default=str)


# --- Scenario 2 ---


@pytest.mark.asyncio
async def test_scenario_2_vague_past_reference_empty_db(db_session, dev_settings):
    request = "Почему я тогда проиграла?"
    resolution = await resolve_past_event(
        db_session,
        user_input=request,
        user_id=USER,
        session_id=SESSION,
        reference=REF,
        app_settings=Settings(openai_api_key=""),
    )
    _, trace, analyst = await _run_analyst(db_session, request, dev_settings=dev_settings)

    content = (analyst.get("content") or "").lower()
    passed = (
        trace.get("is_past_event_request") is True
        and trace.get("inline_facts_in_message") is False
        and trace.get("retrieved_memory_items", {}).get("count") == 0
        and trace.get("llm_called") is False
        and analyst.get("analysis") is None
        and ("не нашёл" in content or "опиши" in content or "истори" in content)
    )
    assert_past_event_llm_invariant(
        trace_from_past_event_resolution(
            user_input=request,
            state={"routed_agent": "analyst"},
            past=resolution,
        )
    )

    result = ScenarioResult(
        name="2_vague_past_empty_db",
        request=request,
        analyst_trace=trace,
        response_text=analyst.get("content") or "",
        analysis=analyst.get("analysis"),
        llm_called=bool(trace.get("llm_called")),
        passed=passed,
    )
    assert result.passed, json.dumps(result.__dict__, ensure_ascii=False, indent=2, default=str)


# --- Scenario 3 ---


@pytest.mark.asyncio
async def test_scenario_3_inline_facts_current_message(db_session, dev_settings):
    request = (
        "Сегодня была тренировка: я плохо двигалась назад, "
        "устала к концу, часто ошибалась на бэкхенде"
    )
    resolution = await resolve_past_event(
        db_session,
        user_input=request,
        user_id=USER,
        session_id=SESSION,
        reference=REF,
        app_settings=Settings(openai_api_key=""),
    )
    _, trace, analyst = await _run_analyst(db_session, request, dev_settings=dev_settings)

    prompt_blob = json.dumps(trace.get("final_prompt_sent_to_llm") or {}, ensure_ascii=False)
    passed = (
        trace.get("inline_facts_in_message") is True
        and trace.get("llm_called") is True
        and trace.get("retrieved_memory_items", {}).get("count") == 0
        and _trace_items_not_from_ltm(trace)
        and analyst.get("analysis") is not None
        and "бэкхенд" in prompt_blob or "тренировка" in prompt_blob
    )

    result = ScenarioResult(
        name="3_inline_facts",
        request=request,
        analyst_trace=trace,
        response_text=(analyst.get("content") or "")[:500],
        analysis=analyst.get("analysis"),
        llm_called=bool(trace.get("llm_called")),
        passed=passed,
        notes=f"is_past_event_query={resolution.is_past_event_query}",
    )
    assert result.passed, json.dumps(result.__dict__, ensure_ascii=False, indent=2, default=str)


# --- Scenario 4 ---


@pytest.mark.asyncio
async def test_scenario_4_saved_training_grounded(db_session, dev_settings):
    request = "Разбери мою последнюю тренировку"
    await _seed_training(db_session, event_date=date(2026, 5, 28))
    resolution = await resolve_past_event(
        db_session,
        user_input=request,
        user_id=USER,
        session_id=SESSION,
        reference=REF,
        app_settings=Settings(openai_api_key=""),
    )
    _, trace, analyst = await _run_analyst(db_session, request, dev_settings=dev_settings)

    items = trace.get("retrieved_memory_items", {}).get("items", [])
    prompt_blob = json.dumps(trace.get("final_prompt_sent_to_llm") or {}, ensure_ascii=False)

    passed = (
        trace.get("structured_function_called") == "find_last_training"
        and trace.get("retrieved_memory_items", {}).get("count") == 1
        and items
        and items[0].get("event_date") == "2026-05-28"
        and trace.get("llm_called") is True
        and "PAST EVENT GROUNDING" in prompt_blob
        and "2026-05-28" in prompt_blob
        and analyst.get("past_event_status") == "grounded"
        and bool((analyst.get("content") or "").strip())
    )

    result = ScenarioResult(
        name="4_saved_training",
        request=request,
        analyst_trace=trace,
        response_text=(analyst.get("content") or "")[:300],
        analysis=analyst.get("analysis"),
        llm_called=bool(trace.get("llm_called")),
        passed=passed,
    )
    assert result.passed, json.dumps(result.__dict__, ensure_ascii=False, indent=2, default=str)


# --- Scenario 5 ---


@pytest.mark.asyncio
async def test_scenario_5_wrong_date_no_fake_analysis(db_session, dev_settings):
    request = "Разбери матч 15 апреля"
    await _seed_match(db_session, event_date=date(2026, 4, 16))
    resolution = await resolve_past_event(
        db_session,
        user_input=request,
        user_id=USER,
        session_id=SESSION,
        reference=REF,
        app_settings=Settings(openai_api_key=""),
    )
    _, trace, analyst = await _run_analyst(db_session, request, dev_settings=dev_settings)

    parsed = trace.get("event_date_parsed") or resolution.retrieval.event_date_parsed
    passed = (
        parsed == "2026-04-15"
        and trace.get("retrieved_memory_items", {}).get("count") == 0
        and trace.get("llm_called") is False
        and analyst.get("analysis") is None
        and trace.get("semantic_fallback_used") is False
        and _no_fake_analysis_cards(analyst.get("content") or "", analyst.get("analysis"))
    )
    assert_past_event_llm_invariant(
        trace_from_past_event_resolution(
            user_input=request,
            state={"routed_agent": "analyst"},
            past=resolution,
        )
    )

    result = ScenarioResult(
        name="5_wrong_date",
        request=request,
        analyst_trace=trace,
        response_text=analyst.get("content") or "",
        analysis=analyst.get("analysis"),
        llm_called=bool(trace.get("llm_called")),
        passed=passed,
    )
    assert result.passed, json.dumps(result.__dict__, ensure_ascii=False, indent=2, default=str)
