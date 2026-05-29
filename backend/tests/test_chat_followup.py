"""Context-aware yes/no follow-up after assistant offers (real graph path)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.graph.runner import run_chat_graph
from app.graph.semantic_router import (
    MemoryAction,
    SemanticTurnDecision,
    TurnIntent,
)
from app.memory.models import Base

USER = "followup-test"
SESSION = "main"
MSG_HEALTH = "как восстановиться после того, как подвернула голеностоп?"
HEALTH_OFFER_REPLY = (
    "Сначала разгрузка и лёд. Хочешь, вместе разберём восстановление по пунктам? (да/нет)"
)
BREAKDOWN_REPLY = (
    "Хорошо, давай разберём по пунктам:\n"
    "1. Что произошло с голеностопом\n"
    "2. Первые 24–48 часов\n"
    "3. Возврат к нагрузке\n"
    "4. Опасные признаки\n"
    "5. Адаптация тренировки"
)
PAST_LOOKUP = "разбери мою тренировку 28 мая"


def _health_advice_decision() -> SemanticTurnDecision:
    return SemanticTurnDecision(
        turn_intent=TurnIntent.ADVICE_REQUEST,
        health_signal=True,
        memory_action=MemoryAction.READ,
        recommended_agent="health_coach",
        reason="test: health advice",
    )


def _past_lookup_decision() -> SemanticTurnDecision:
    return SemanticTurnDecision(
        turn_intent=TurnIntent.PAST_EVENT_LOOKUP_REQUEST,
        event_type="training",
        has_inline_facts=False,
        memory_action=MemoryAction.READ,
        recommended_agent="analyst",
        reason="test: past lookup",
    )


@pytest.fixture
async def memory_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _run_turn(
    session: AsyncSession,
    message: str,
    *,
    thread_id: str,
    router_side_effect: list[SemanticTurnDecision] | None = None,
    llm_side_effect: list[str] | None = None,
) -> dict:
    settings = Settings(openai_api_key="sk-test", development_mode=True)
    router_iter = iter(router_side_effect or [])
    llm_iter = iter(llm_side_effect or [])

    async def _route(*_a, **_k):
        return next(router_iter)

    async def _llm(*_a, **_k):
        return next(llm_iter)

    with (
        patch("app.graph.runner.settings", settings),
        patch("app.graph.nodes.settings", settings),
        patch("app.graph.nodes.route_user_turn", side_effect=_route),
        patch("app.graph.llm.acompletion", side_effect=_llm),
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
            session,
            message=message,
            user_id=USER,
            session_id=SESSION,
            thread_id=thread_id,
        )


@pytest.mark.asyncio
async def test_health_followup_yes_uses_pending_context(memory_db: AsyncSession):
    tid = str(uuid.uuid4())
    turn1 = await _run_turn(
        memory_db,
        MSG_HEALTH,
        thread_id=tid,
        router_side_effect=[_health_advice_decision()],
        llm_side_effect=[HEALTH_OFFER_REPLY],
    )
    assert turn1.get("agents_used") == ["health_coach"]
    assert "да/нет" in (turn1.get("message") or "").lower() or "(да/нет)" in (
        turn1.get("message") or ""
    )

    turn2 = await _run_turn(
        memory_db,
        "да",
        thread_id=tid,
        router_side_effect=[],  # must not be called
        llm_side_effect=[BREAKDOWN_REPLY],
    )
    msg = (turn2.get("message") or "").lower()
    assert turn2.get("agents_used") == ["health_coach"]
    assert "привет" not in msg
    assert "как я могу помочь" not in msg
    assert any(x in msg for x in ("пункт", "голеностоп", "24", "нагрузк"))


@pytest.mark.asyncio
async def test_health_followup_no_polite_close(memory_db: AsyncSession):
    tid = str(uuid.uuid4())
    await _run_turn(
        memory_db,
        MSG_HEALTH,
        thread_id=tid,
        router_side_effect=[_health_advice_decision()],
        llm_side_effect=[HEALTH_OFFER_REPLY],
    )
    turn2 = await _run_turn(
        memory_db,
        "нет",
        thread_id=tid,
        router_side_effect=[],
        llm_side_effect=[],
    )
    msg = turn2.get("message") or ""
    assert "привет" not in msg.lower()
    assert "привет" not in msg.lower()
    assert len(msg) > 10


@pytest.mark.asyncio
async def test_bare_yes_without_pending_asks_clarification(memory_db: AsyncSession):
    tid = str(uuid.uuid4())
    turn = await _run_turn(
        memory_db,
        "да",
        thread_id=tid,
        router_side_effect=[],
        llm_side_effect=[],
    )
    msg = turn.get("message") or ""
    assert turn.get("agents_used") == ["direct"]
    assert "к чему" in msg.lower() or "уточни" in msg.lower()


@pytest.mark.asyncio
async def test_topic_change_clears_pending_and_routes_normally(memory_db: AsyncSession):
    tid = str(uuid.uuid4())
    await _run_turn(
        memory_db,
        MSG_HEALTH,
        thread_id=tid,
        router_side_effect=[_health_advice_decision()],
        llm_side_effect=[HEALTH_OFFER_REPLY],
    )
    turn2 = await _run_turn(
        memory_db,
        PAST_LOOKUP,
        thread_id=tid,
        router_side_effect=[_past_lookup_decision()],
        llm_side_effect=["Краткий разбор тренировки."],
    )
    assert turn2.get("agents_used") == ["analyst"]
    assert "к чему именно ты отвечаешь" not in (turn2.get("message") or "").lower()
