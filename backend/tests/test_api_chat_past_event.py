"""
Integration: real run_chat_graph path (same as POST /api/chat).

Proves dated past-event requests cannot use generic hybrid memories or semantic fallback.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import json

from app.config import Settings
from app.graph.semantic_router import (
    MemoryAction,
    SemanticTurnDecision,
    TurnIntent,
)
from app.graph.response_assembly import (
    assemble_chat_payload,
    assert_past_event_api_invariant,
    enforce_blocked_past_event_response,
)
from app.graph.runner import run_chat_graph
from app.memory.models import Base, ExtractedMemoryType, Memory, MemoryLayer, Turn

USER = "e2e-aigerim"
SESSION = "main"
BUILD_ID = "semantic-router-v1"
MSG_LAST = "Разбери мою последнюю тренировку"
MSG_FEB = "Разбери мою тренировку 10го февраля которая была"
MSG_YESTERDAY_LOG = (
    "вчера была тренировка: бег 5 км, многоваланка, подвернула голеностоп"
)
MSG_LOOKUP_FEB8 = "Разбери мою тренировку 8 февраля"


@pytest.fixture
async def db_with_generic_memories_only():
    """Five unrelated episodic rows — none on 2026-02-10."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        for i, (ed, val) in enumerate(
            [
                (date(2026, 5, 28), "Силовая недавняя"),
                (date(2026, 4, 20), "Интервальная апрель"),
                (date(2026, 3, 1), "Техника март"),
                (date(2026, 1, 15), "Силовая январь"),
                (None, "Pending без даты"),
            ]
        ):
            turn = Turn(
                session_id=SESSION,
                user_id=USER,
                messages=[{"role": "user", "content": val}],
                turn_timestamp=datetime.now(timezone.utc),
            )
            session.add(turn)
            await session.flush()
            session.add(
                Memory(
                    user_id=USER,
                    source_session=SESSION,
                    source_turn_id=turn.id,
                    key=f"training.generic.{i}",
                    value=val,
                    memory_type=ExtractedMemoryType.event,
                    memory_layer=MemoryLayer.episodic,
                    event_type="training_log",
                    session_type="training",
                    event_date=ed,
                    confidence=0.9,
                    importance=0.8,
                    active=True,
                )
            )
        await session.flush()
        yield session
    await engine.dispose()


def _past_lookup_router_decision() -> SemanticTurnDecision:
    return SemanticTurnDecision(
        turn_intent=TurnIntent.PAST_EVENT_LOOKUP_REQUEST,
        event_type="training",
        has_inline_facts=False,
        memory_action=MemoryAction.READ,
        recommended_agent="analyst",
        reason="test: past lookup",
    )


def _new_event_log_router_decision() -> SemanticTurnDecision:
    return SemanticTurnDecision(
        turn_intent=TurnIntent.NEW_EVENT_LOG,
        event_type="training",
        has_inline_facts=True,
        inline_facts_summary="бег 5 км, многоваланка, подвернула голеностоп",
        health_signal=True,
        memory_action=MemoryAction.WRITE,
        recommended_agent="analyst",
        reason="test: new event log",
    )


async def _run_graph_with_router(
    db: AsyncSession,
    message: str,
    router_decision: SemanticTurnDecision,
    *,
    thread_id: str | None = None,
    llm_reply: str = "Учти нагрузку на голеностоп и снизь интенсивность на 2–3 дня.",
) -> dict:
    settings = Settings(openai_api_key="sk-test", development_mode=True)
    with (
        patch("app.graph.runner.settings", settings),
        patch("app.graph.nodes.settings", settings),
        patch(
            "app.graph.nodes.route_user_turn",
            new_callable=AsyncMock,
            return_value=router_decision,
        ),
        patch(
            "app.graph.llm.acompletion",
            new_callable=AsyncMock,
            return_value=llm_reply,
        ),
        patch("app.memory.embeddings.embed_query", new_callable=AsyncMock, return_value=None),
        patch("app.graph.runner._persist_turn_memories", new_callable=AsyncMock) as mock_persist,
        patch("app.graph.runner._persist_interaction_offer", new_callable=AsyncMock),
        patch("app.graph.runner.get_compiled_graph") as mock_graph,
    ):
        from langgraph.checkpoint.memory import MemorySaver

        from app.graph.build import build_graph

        graph = build_graph().compile(checkpointer=MemorySaver())
        mock_graph.return_value = graph
        result = await run_chat_graph(
            db,
            message=message,
            user_id=USER,
            session_id=SESSION,
            thread_id=thread_id or str(uuid.uuid4()),
        )
        result["_persist_called"] = mock_persist.called
        result["_memory_write_scheduled"] = result.get("memory_write_scheduled")
        return result


async def _run_graph(
    db: AsyncSession,
    message: str,
    *,
    development_mode: bool = True,
) -> dict:
    settings = Settings(openai_api_key="sk-test", development_mode=development_mode)

    with (
        patch("app.graph.runner.settings", settings),
        patch("app.graph.nodes.settings", settings),
        patch(
            "app.graph.nodes.route_user_turn",
            new_callable=AsyncMock,
            return_value=_past_lookup_router_decision(),
        ),
        patch("app.graph.llm.acompletion", new_callable=AsyncMock) as mock_llm,
        patch("app.memory.embeddings.embed_query", new_callable=AsyncMock, return_value=None),
        patch("app.graph.runner._persist_turn_memories", new_callable=AsyncMock),
        patch("app.graph.runner._persist_interaction_offer", new_callable=AsyncMock),
        patch("app.graph.runner.get_compiled_graph") as mock_graph,
    ):
        from langgraph.checkpoint.memory import MemorySaver

        from app.graph.build import build_graph

        graph = build_graph().compile(checkpointer=MemorySaver())
        mock_graph.return_value = graph

        return await run_chat_graph(
            db,
            message=message,
            user_id=USER,
            session_id=SESSION,
            thread_id=str(uuid.uuid4()),
        )


def _assert_blocked_past_event(result: dict, mock_llm: AsyncMock, *, february: bool = False):
    mock_llm.assert_not_called()
    assert result.get("debug_build_id") == BUILD_ID
    assert result["analysis"] is None
    assert result.get("comparison_status") == "not_found"
    assert result.get("memory_citations_count", 0) >= 0

    msg = (result.get("message") or "").lower()
    assert "не нашёл" in msg
    for banned in (
        "physical_fatigue",
        "tactical_gap",
        "psychological",
        "technical",
        "физическая усталость",
    ):
        assert banned not in msg

    trace = result.get("analyst_trace") or {}
    assert trace.get("is_past_event_request") is True
    assert trace.get("llm_called") is False
    assert trace.get("inline_facts_in_message") is False
    assert trace.get("retrieved_memory_items", {}).get("count") == 0
    assert trace.get("semantic_fallback_used") is False
    assert trace.get("blocked_reason") in (
        "past_event_not_found",
        "past_event_no_retrieved_memory",
        "pending_event_date_unknown",
    )

    if february:
        assert trace.get("event_date_parsed") == "2026-02-10"
        assert trace.get("structured_function_called") == "find_training_by_date"
        assert "феврал" in msg or "10" in msg


@pytest.mark.asyncio
async def test_new_event_log_no_overwrite_crash():
    """Regression: turn_decision Overwrite({}) must not crash .get() in graph nodes."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        result = await _run_graph_with_router(
            session,
            MSG_YESTERDAY_LOG,
            _new_event_log_router_decision(),
        )
    await engine.dispose()

    assert result.get("debug_build_id") == BUILD_ID
    assert result.get("comparison_status") != "not_found"
    msg = (result.get("message") or "").lower()
    assert "не нашёл" not in msg
    assert any(w in msg for w in ("голеностоп", "нагрузк", "трениров", "восстанов"))
    trace = result.get("analyst_trace") or {}
    assert trace.get("turn_intent") == "NEW_EVENT_LOG"
    assert trace.get("has_inline_facts") is True or trace.get("inline_facts_in_message")
    assert result.get("_persist_called") is False
    assert result.get("_memory_write_scheduled") is True


@pytest.mark.asyncio
async def test_same_thread_not_found_then_new_event_log():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    tid = str(uuid.uuid4())
    async with factory() as session:
        blocked = await _run_graph_with_router(
            session,
            MSG_LOOKUP_FEB8,
            _past_lookup_router_decision(),
            thread_id=tid,
            llm_reply="unused",
        )
        assert blocked.get("comparison_status") == "not_found"

        result = await _run_graph_with_router(
            session,
            MSG_YESTERDAY_LOG,
            _new_event_log_router_decision(),
            thread_id=tid,
        )
    await engine.dispose()

    assert result.get("debug_build_id") == BUILD_ID
    assert result.get("comparison_status") != "not_found"
    trace = result.get("analyst_trace") or {}
    assert trace.get("turn_intent") == "NEW_EVENT_LOG"
    assert "не нашёл" not in (result.get("message") or "").lower()


@pytest.mark.asyncio
async def test_run_chat_graph_empty_db_last_training_blocked():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        with patch("app.graph.llm.acompletion", new_callable=AsyncMock) as mock_llm:
            result = await _run_graph(session, MSG_LAST)
        _assert_blocked_past_event(result, mock_llm)
    await engine.dispose()


@pytest.mark.asyncio
async def test_same_thread_second_turn_not_polluted_by_first(db_with_generic_memories_only: AsyncSession):
    """Checkpoint thread: turn 1 LLM fake analysis, turn 2 blocked — API must be honest."""
    tid = str(uuid.uuid4())
    settings = Settings(openai_api_key="sk-test", development_mode=True)
    planner_json = (
        '{"agents": ["analyst"], "interaction_mode": "full_analysis", '
        '"reason": "test", "needs_confirmation": false, "needs_memory": true}'
    )
    fake_analysis_body = (
        '{"summary":"x","errors":[{"category":"physical_fatigue","severity":"HIGH"},'
        '{"category":"tactical_gap","severity":"MED"}]}'
    )
    async def fake_acompletion(*_a, **_k):
        return fake_analysis_body

    with (
        patch("app.graph.runner.settings", settings),
        patch("app.graph.nodes.settings", settings),
        patch(
            "app.graph.nodes.route_user_turn",
            new_callable=AsyncMock,
            return_value=_past_lookup_router_decision(),
        ),
        patch("app.graph.llm.acompletion", side_effect=fake_acompletion),
        patch("app.memory.embeddings.embed_query", new_callable=AsyncMock, return_value=None),
        patch("app.graph.runner._persist_turn_memories", new_callable=AsyncMock),
        patch("app.graph.runner._persist_interaction_offer", new_callable=AsyncMock),
        patch("app.graph.runner.get_compiled_graph") as mock_graph,
    ):
        from langgraph.checkpoint.memory import MemorySaver

        from app.graph.build import build_graph

        graph = build_graph().compile(checkpointer=MemorySaver())
        mock_graph.return_value = graph

        await run_chat_graph(
            db_with_generic_memories_only,
            message="Разбери последнюю тренировку",
            user_id=USER,
            session_id=SESSION,
            thread_id=tid,
        )
        with patch("app.graph.llm.acompletion", new_callable=AsyncMock) as mock_llm:
            result = await run_chat_graph(
                db_with_generic_memories_only,
                message=MSG_FEB,
                user_id=USER,
                session_id=SESSION,
                thread_id=tid,
            )
        _assert_blocked_past_event(result, mock_llm, february=True)


@pytest.mark.asyncio
async def test_dated_feb10_blocks_despite_generic_memories(db_with_generic_memories_only: AsyncSession):
    """
    Real failure case: memory_citations_count>0 but dated request must not call LLM.
    """
    with patch("app.graph.llm.acompletion", new_callable=AsyncMock) as mock_llm:
        result = await _run_graph(db_with_generic_memories_only, MSG_FEB)
    _assert_blocked_past_event(result, mock_llm, february=True)
    # In production, hybrid recall may set memory_citations_count>0; LLM must still be blocked.


def test_assemble_ignores_stale_first_analyst_output():
    """Reproduces checkpoint pollution: first analyst fake, last analyst blocked."""
    stale_fake = {
        "agent": "analyst",
        "content": "Физическая усталость HIGH. tactical_gap MED.",
        "analysis": {
            "errors": [
                {"category": "physical_fatigue", "severity": "HIGH"},
                {"category": "tactical_gap", "severity": "MED"},
            ]
        },
        "llm_called": True,
        "comparison_status": None,
    }
    blocked = {
        "agent": "analyst",
        "content": "Я не нашёл в памяти тренировку 10 февраля 2026.",
        "analysis": None,
        "llm_called": False,
        "comparison_status": "not_found",
        "chat_actions": [{"id": "add_training", "label": "Добавить тренировку"}],
        "analyst_trace": {
            "is_past_event_request": True,
            "llm_called": False,
            "blocked_reason": "past_event_not_found",
            "event_date_parsed": "2026-02-10",
            "retrieved_memory_items": {"count": 0, "items": []},
        },
    }
    graph_result = {
        "final_response": stale_fake["content"],
        "agent_outputs": [stale_fake, blocked],
        "analyst_trace": blocked["analyst_trace"],
        "agents_used": ["analyst"],
    }
    payload = enforce_blocked_past_event_response(assemble_chat_payload(graph_result))
    assert_past_event_api_invariant(payload)

    blob = json.dumps(payload, ensure_ascii=False).lower()
    assert payload["analysis"] is None
    assert payload["comparison_status"] == "not_found"
    assert "не нашёл" in payload["message"].lower()
    assert "physical_fatigue" not in blob
    assert "tactical_gap" not in blob
    assert "физическая усталость" not in blob


@pytest.mark.asyncio
async def test_semantic_fallback_disabled_for_dated_intent(db_with_generic_memories_only: AsyncSession):
    from app.memory.past_event_guard import resolve_past_event

    resolution = await resolve_past_event(
        db_with_generic_memories_only,
        user_input=MSG_FEB,
        user_id=USER,
        session_id=SESSION,
        reference=date(2026, 5, 29),
        app_settings=Settings(openai_api_key=""),
    )
    assert resolution.is_past_event_request
    assert not resolution.found
    assert not resolution.llm_allowed
    assert not resolution.retrieval.semantic_fallback_used
    assert resolution.retrieval.event_date_parsed == "2026-02-10"
