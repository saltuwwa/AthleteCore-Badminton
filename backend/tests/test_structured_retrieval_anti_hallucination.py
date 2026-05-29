"""
Anti-hallucination matrix: structured retrieval + past_event_guard + Analyst trace.

Each test proves a specific failure mode cannot reach the LLM without grounded memory.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.graph.analyst_trace import trace_from_past_event_resolution
from app.graph.nodes import analyst_node
from app.memory.models import Base, ExtractedMemoryType, Memory, MemoryLayer, Turn
from app.memory.past_event_guard import resolve_past_event
from app.memory.structured_retrieval import (
    CONF_LAST_NULL_DATE_FALLBACK,
    find_last_training,
    find_match_by_date,
    find_match_by_day_month,
)

USER = "athlete-matrix"
SESSION = "main"
REF = date(2026, 5, 29)


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed(
    session: AsyncSession,
    *,
    key: str,
    value: str,
    event_type: str,
    session_type: str,
    event_date: date | None,
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
        key=key,
        value=value,
        memory_type=ExtractedMemoryType.event,
        memory_layer=MemoryLayer.episodic,
        event_type=event_type,
        session_type=session_type,
        event_date=event_date,
        confidence=0.9,
        importance=0.8,
        active=True,
    )
    session.add(mem)
    await session.flush()
    return mem


def _assert_retrieval_trace(
    resolution,
    *,
    structured_retrieval_used: bool | None = None,
    structured_function_called: str | None = None,
    retrieved_count: int | None = None,
    semantic_fallback_used: bool | None = None,
    llm_allowed: bool | None = None,
    blocked_reason: str | None = None,
    event_date_parsed: str | None = None,
    event_date_parsed_contains: str | None = None,
):
    rt = resolution.retrieval
    if structured_retrieval_used is not None:
        assert rt.structured_retrieval_used is structured_retrieval_used
    if structured_function_called is not None:
        assert rt.structured_function_called == structured_function_called
    if retrieved_count is not None:
        assert len(rt.retrieved_memory_items) == retrieved_count
    if semantic_fallback_used is not None:
        assert rt.semantic_fallback_used is semantic_fallback_used
    if llm_allowed is not None:
        assert resolution.llm_allowed is llm_allowed
    if blocked_reason is not None:
        assert rt.blocked_reason == blocked_reason
    if event_date_parsed is not None:
        assert rt.event_date_parsed == event_date_parsed
    if event_date_parsed_contains is not None:
        assert event_date_parsed_contains in (rt.event_date_parsed or "")


def _analyst_trace(resolution, user_input: str):
    trace = trace_from_past_event_resolution(
        user_input=user_input,
        state={"routed_agent": "analyst", "interaction_mode": "full_analysis"},
        past=resolution,
    )
    trace.apply_past_event_invariant()
    return trace


# --- Scenario 1: empty memory ---


@pytest.mark.asyncio
async def test_empty_memory_blocks_llm_and_skips_analysis_cards(db_session: AsyncSession):
    """No LTM row → honest not-found; Analyst must not invent HIGH/MED cards."""
    user_input = "Разбери мою последнюю тренировку"
    resolution = await resolve_past_event(
        db_session,
        user_input=user_input,
        user_id=USER,
        session_id=SESSION,
        reference=REF,
        app_settings=Settings(openai_api_key=""),
    )
    assert resolution.is_past_event_request
    assert not resolution.found
    _assert_retrieval_trace(
        resolution,
        structured_retrieval_used=True,
        structured_function_called="find_last_training",
        retrieved_count=0,
        semantic_fallback_used=False,
        llm_allowed=False,
        blocked_reason="past_event_not_found",
    )

    trace = _analyst_trace(resolution, user_input)
    assert trace.llm_called is False
    assert trace.retrieved_memory_items_count == 0
    payload = trace.to_dict()
    assert payload["llm_called"] is False
    assert payload["blocked_reason"]
    assert payload["parsed_json_response"] is None

    out = await analyst_node(
        {
            "user_input": user_input,
            "user_id": USER,
            "session_id": SESSION,
            "interaction_mode": "full_analysis",
            "memory_context": "",
            "memory_citations": [],
            "turn_decision": {
                "turn_intent": "PAST_EVENT_LOOKUP_REQUEST",
                "has_inline_facts": False,
                "memory_action": "read",
            },
        },
        {"configurable": {"db_session": db_session}},
    )
    analyst = out["agent_outputs"][0]
    assert analyst["analysis"] is None
    assert out["llm_called"] is False
    assert analyst["past_event_status"] == "not_found"
    content = (analyst["content"] or "").lower()
    assert "последнюю тренировку" in content or "не нашёл" in content
    for hallucination_marker in ("high", "med", "усталост", "тактик", "психолог"):
        assert hallucination_marker not in content


# --- Scenario 2: latest training ---


@pytest.mark.asyncio
async def test_latest_training_sql_returns_newest_event_date(db_session: AsyncSession):
    await _seed(
        db_session,
        key="training.old",
        value="Old",
        event_type="training_log",
        session_type="training",
        event_date=date(2026, 5, 20),
    )
    await _seed(
        db_session,
        key="training.latest",
        value="Latest",
        event_type="training_log",
        session_type="training",
        event_date=date(2026, 5, 28),
    )
    hit = await find_last_training(db_session, USER, session_id=SESSION)
    assert hit is not None
    assert hit.memory.event_date == date(2026, 5, 28)

    resolution = await resolve_past_event(
        db_session,
        user_input="Разбери мою последнюю тренировку",
        user_id=USER,
        session_id=SESSION,
        reference=REF,
        app_settings=Settings(openai_api_key=""),
    )
    assert resolution.found
    assert resolution.llm_allowed
    _assert_retrieval_trace(
        resolution,
        structured_retrieval_used=True,
        structured_function_called="find_last_training",
        retrieved_count=1,
        semantic_fallback_used=False,
    )
    assert resolution.retrieval.retrieved_memory_items[0].event_date == "2026-05-28"


# --- Scenario 3: exact date match ---


@pytest.mark.asyncio
async def test_exact_date_match_april_15(db_session: AsyncSession):
    target = date(2026, 4, 15)
    await _seed(
        db_session,
        key="match.apr15",
        value="Match 15 April",
        event_type="match_log",
        session_type="match",
        event_date=target,
    )
    by_date = await find_match_by_date(db_session, USER, target, session_id=SESSION)
    assert by_date is not None
    assert by_date.memory.event_date == target

    resolution = await resolve_past_event(
        db_session,
        user_input="Разбери матч 15 апреля",
        user_id=USER,
        session_id=SESSION,
        reference=REF,
        app_settings=Settings(openai_api_key=""),
    )
    assert resolution.found
    assert resolution.llm_allowed
    assert resolution.retrieval.structured_function_called in (
        "find_match_by_date",
        "find_match_by_day_month",
    )
    _assert_retrieval_trace(
        resolution,
        structured_retrieval_used=True,
        retrieved_count=1,
    )
    assert resolution.retrieval.retrieved_memory_items[0].event_date == "2026-04-15"


# --- Scenario 4: wrong date (16th must not pass as 15th) ---


@pytest.mark.asyncio
async def test_wrong_date_does_not_accept_nearby_match(db_session: AsyncSession):
    await _seed(
        db_session,
        key="match.apr16",
        value="Match 16 April only",
        event_type="match_log",
        session_type="match",
        event_date=date(2026, 4, 16),
    )
    day_month = await find_match_by_day_month(
        db_session,
        USER,
        day=15,
        month=4,
        reference=REF,
        session_id=SESSION,
    )
    assert day_month is None

    resolution = await resolve_past_event(
        db_session,
        user_input="Разбери матч 15 апреля",
        user_id=USER,
        session_id=SESSION,
        reference=REF,
        query_embedding=None,
        app_settings=Settings(openai_api_key=""),
    )
    assert not resolution.found
    assert not resolution.llm_allowed
    assert resolution.retrieval.structured_function_called in (
        "find_match_by_date",
        "find_match_by_day_month",
    )
    _assert_retrieval_trace(
        resolution,
        structured_retrieval_used=True,
        retrieved_count=0,
        llm_allowed=False,
        blocked_reason="past_event_not_found",
    )
    trace = _analyst_trace(resolution, "Разбери матч 15 апреля")
    assert trace.llm_called is False


# --- Scenario 5: null event_date pending ---


@pytest.mark.asyncio
async def test_null_event_date_pending_not_treated_as_dated_training(db_session: AsyncSession):
    await _seed(
        db_session,
        key="training.pending",
        value="Pending log without date",
        event_type="training_log",
        session_type="training",
        event_date=None,
    )
    hit = await find_last_training(db_session, USER, session_id=SESSION)
    assert hit is not None
    assert hit.confidence == CONF_LAST_NULL_DATE_FALLBACK
    assert hit.memory.event_date is None

    resolution = await resolve_past_event(
        db_session,
        user_input="Разбери последнюю тренировку",
        user_id=USER,
        session_id=SESSION,
        reference=REF,
        app_settings=Settings(openai_api_key=""),
    )
    assert not resolution.found
    assert not resolution.llm_allowed
    _assert_retrieval_trace(
        resolution,
        structured_retrieval_used=True,
        structured_function_called="find_last_training",
        retrieved_count=1,
        llm_allowed=False,
        blocked_reason="pending_event_date_unknown",
    )
    item = resolution.retrieval.retrieved_memory_items[0]
    assert item.event_date is None
    assert "pending" in (item.match_reason or "")
    reason = resolution.retrieval.date_normalization_reason or ""
    assert reason == "event_date_unknown" or "unknown" in reason or resolution.retrieval.blocked_reason == "pending_event_date_unknown"

    trace = _analyst_trace(resolution, "Разбери последнюю тренировку")
    assert trace.llm_called is False
    assert trace.retrieved_memory_items_count == 1


# --- Scenario 6: yesterday ---


@pytest.mark.asyncio
async def test_yesterday_resolves_to_previous_calendar_day(db_session: AsyncSession):
    await _seed(
        db_session,
        key="training.yesterday",
        value="Training yesterday",
        event_type="training_log",
        session_type="training",
        event_date=date(2026, 5, 28),
    )
    resolution = await resolve_past_event(
        db_session,
        user_input="Разбери тренировку вчера",
        user_id=USER,
        session_id=SESSION,
        reference=REF,
        app_settings=Settings(openai_api_key=""),
    )
    assert resolution.found
    assert resolution.llm_allowed
    _assert_retrieval_trace(
        resolution,
        structured_retrieval_used=True,
        structured_function_called="find_training_by_date",
        retrieved_count=1,
        event_date_parsed_contains="2026-05-28",
    )
    assert resolution.retrieval.retrieved_memory_items[0].event_date == "2026-05-28"
