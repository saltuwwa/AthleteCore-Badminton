"""Integration tests for SQL structured retrieval API."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.memory.models import Base, ExtractedMemoryType, Memory, MemoryLayer, Turn
from app.memory.structured_retrieval import (
    CONF_LAST_NULL_DATE_FALLBACK,
    find_events_by_date_range,
    find_last_match,
    find_last_training,
    find_match_by_date,
    find_training_by_date,
)

USER = "athlete-1"
SESSION = "main"


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _insert_memory(
    session: AsyncSession,
    *,
    key: str,
    value: str,
    event_type: str,
    session_type: str,
    event_date: date | None,
    created_offset: int = 0,
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
    if created_offset:
        mem.created_at = datetime(
            2026, 5, 20 + created_offset, 12, 0, tzinfo=timezone.utc
        )
        await session.flush()
    return mem


@pytest.mark.asyncio
async def test_find_last_training_orders_by_event_date(db_session: AsyncSession):
    await _insert_memory(
        db_session,
        key="training.session.old",
        value="Old training",
        event_type="training_log",
        session_type="training",
        event_date=date(2026, 5, 20),
    )
    await _insert_memory(
        db_session,
        key="training.session.latest",
        value="Latest training",
        event_type="training_log",
        session_type="training",
        event_date=date(2026, 5, 28),
    )
    hit = await find_last_training(db_session, USER, session_id=SESSION)
    assert hit is not None
    assert hit.memory.event_date == date(2026, 5, 28)
    assert hit.confidence >= 0.9


@pytest.mark.asyncio
async def test_find_last_training_fallback_null_date_low_confidence(db_session: AsyncSession):
    await _insert_memory(
        db_session,
        key="training.session.pending",
        value="Pending training log",
        event_type="training_log",
        session_type="training",
        event_date=None,
    )
    hit = await find_last_training(db_session, USER, session_id=SESSION)
    assert hit is not None
    assert hit.confidence == CONF_LAST_NULL_DATE_FALLBACK
    assert hit.memory.event_date is None


@pytest.mark.asyncio
async def test_find_last_match(db_session: AsyncSession):
    await _insert_memory(
        db_session,
        key="match.latest",
        value="Match A",
        event_type="match_log",
        session_type="match",
        event_date=date(2026, 4, 10),
    )
    await _insert_memory(
        db_session,
        key="match.other",
        value="Match B",
        event_type="match_log",
        session_type="match",
        event_date=date(2026, 4, 15),
    )
    hit = await find_last_match(db_session, USER, session_id=SESSION)
    assert hit is not None
    assert hit.memory.event_date == date(2026, 4, 15)


@pytest.mark.asyncio
async def test_find_match_and_training_by_date(db_session: AsyncSession):
    target = date(2026, 4, 15)
    await _insert_memory(
        db_session,
        key="match.apr15",
        value="Match 15 apr",
        event_type="match_log",
        session_type="match",
        event_date=target,
    )
    await _insert_memory(
        db_session,
        key="training.apr15",
        value="Training 15 apr",
        event_type="training_log",
        session_type="training",
        event_date=target,
    )
    m = await find_match_by_date(db_session, USER, target, session_id=SESSION)
    t = await find_training_by_date(db_session, USER, target, session_id=SESSION)
    assert m is not None and "Match" in m.memory.value
    assert t is not None and "Training" in t.memory.value


@pytest.mark.asyncio
async def test_find_events_by_date_range(db_session: AsyncSession):
    await _insert_memory(
        db_session,
        key="training.1",
        value="T1",
        event_type="training_log",
        session_type="training",
        event_date=date(2026, 5, 18),
    )
    await _insert_memory(
        db_session,
        key="match.1",
        value="M1",
        event_type="match_log",
        session_type="match",
        event_date=date(2026, 5, 22),
    )
    await _insert_memory(
        db_session,
        key="training.out",
        value="T out",
        event_type="training_log",
        session_type="training",
        event_date=date(2026, 6, 1),
    )
    rows = await find_events_by_date_range(
        db_session,
        USER,
        date(2026, 5, 15),
        date(2026, 5, 25),
        session_id=SESSION,
    )
    assert len(rows) == 2
    only_training = await find_events_by_date_range(
        db_session,
        USER,
        date(2026, 5, 1),
        date(2026, 5, 31),
        event_type="training_log",
        session_id=SESSION,
    )
    assert len(only_training) == 1
    assert only_training[0].memory.event_type == "training_log"
