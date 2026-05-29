"""Past-event honest not-found guard (all analyze/compare/recall intents)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.memory.models import Base, ExtractedMemoryType, Memory, MemoryLayer, Turn
from app.memory.past_event_guard import (
    build_not_found_reply,
    is_past_event_request,
    parse_past_event_intent,
    resolve_past_event,
    user_provided_facts_in_message,
)
from app.memory.past_event_intent import detect_past_event_signals

USER = "u1"
SESSION = "main"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Разбери мою последнюю тренировку", True),
        ("Проанализируй прошлый матч", True),
        ("Вспомни, что было тогда на корте", True),
        ("Найди ошибки в последней игре", True),
        ("Сравни с предыдущим матчем", True),
        ("Оцени прогресс по прошлым данным", True),
        ("Какая погода завтра?", False),
        (
            "Вчера была силовая 90 минут, RPE 8, устала на закрытии",
            False,
        ),  # logging facts, not an analyze/recall request
    ],
)
def test_is_past_event_request(text: str, expected: bool):
    assert is_past_event_request(text) is expected


def test_parse_last_training_intent():
    intent = parse_past_event_intent("Разбери мою последнюю тренировку", date(2026, 5, 29))
    assert intent is not None
    assert intent.kind == "last_training"
    assert intent.event_focus == "training"


def test_user_provided_facts_in_message():
    assert user_provided_facts_in_message(
        "Вчера силовая 90 минут, RPE 8, на закрытии не хватало ног"
    )
    assert not user_provided_facts_in_message("Разбери мою последнюю тренировку")
    assert not user_provided_facts_in_message("Почему я тогда проиграла?")


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_resolve_not_found_last_training_empty_db(db_session: AsyncSession):
    resolution = await resolve_past_event(
        db_session,
        user_input="Разбери мою последнюю тренировку",
        user_id=USER,
        session_id=SESSION,
        reference=date(2026, 5, 29),
    )
    assert resolution.is_past_event_request
    assert not resolution.found
    assert not resolution.llm_allowed
    assert "последнюю тренировку" in build_not_found_reply(resolution).lower()
    assert resolution.missing_message
    assert not any(
        w in build_not_found_reply(resolution).lower()
        for w in ("усталост", "тактик", "психолог", "high", "med")
    )


@pytest.mark.asyncio
async def test_resolve_inline_facts_skips_db(db_session: AsyncSession):
    resolution = await resolve_past_event(
        db_session,
        user_input="Разбери: вчера силовая 90 минут, RPE 8, на бэкхенде опоздала с ударом",
        user_id=USER,
        session_id=SESSION,
    )
    assert resolution.is_past_event_request
    assert resolution.found
    assert resolution.inline_facts_in_message
    assert resolution.llm_allowed
    assert "CURRENT message" in resolution.grounding_context


@pytest.mark.asyncio
async def test_resolve_found_with_stored_training(db_session: AsyncSession):
    turn = Turn(
        session_id=SESSION,
        user_id=USER,
        messages=[{"role": "user", "content": "log"}],
        turn_timestamp=datetime.now(timezone.utc),
    )
    db_session.add(turn)
    await db_session.flush()
    db_session.add(
        Memory(
            user_id=USER,
            source_session=SESSION,
            source_turn_id=turn.id,
            key="training.session.latest",
            value="Силовая 90 мин RPE 7",
            memory_type=ExtractedMemoryType.event,
            memory_layer=MemoryLayer.episodic,
            event_type="training_log",
            session_type="training",
            event_date=date(2026, 5, 28),
            confidence=0.9,
            importance=0.8,
            active=True,
        )
    )
    await db_session.flush()

    resolution = await resolve_past_event(
        db_session,
        user_input="Разбери мою последнюю тренировку",
        user_id=USER,
        session_id=SESSION,
    )
    assert resolution.found
    assert resolution.llm_allowed
    assert resolution.matched_memory_ids


def test_detect_signals_progress():
    sig = detect_past_event_signals("Оцени прогресс по прошлым данным")
    assert sig is not None
    assert "assess_progress" in {a.value for a in sig.actions}
