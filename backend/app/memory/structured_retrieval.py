"""SQL-first structured retrieval API over SQLite LTM (sport episodic memories)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .constants import SESSION_MATCH, SESSION_TRAINING
from .models import Memory
from .retrieval import memory_scope_clause

# Confidence scores for read-path routing (structured before semantic fallback).
CONF_LAST_DATED = 0.95
CONF_LAST_NULL_DATE_FALLBACK = 0.42
CONF_EXACT_DATE = 0.98
CONF_DAY_MONTH = 0.96
CONF_DATE_RANGE = 0.9
CONF_OPPONENT = 0.88

DEFAULT_SESSION_ID = "main"


@dataclass(slots=True)
class StructuredMatch:
    memory: Memory
    confidence: float
    match_reason: str


def _scope(user_id: str | None, session_id: str = DEFAULT_SESSION_ID):
    return and_(Memory.active.is_(True), memory_scope_clause(user_id, session_id))


def _training_clause():
    return or_(
        Memory.event_type == "training_log",
        Memory.session_type == SESSION_TRAINING,
    )


def _match_clause():
    return or_(
        Memory.event_type == "match_log",
        Memory.session_type == SESSION_MATCH,
    )


def _order_event_date_created():
    return (Memory.event_date.desc(), Memory.created_at.desc())


async def find_last_training(
    session: AsyncSession,
    user_id: str | None,
    *,
    session_id: str = DEFAULT_SESSION_ID,
) -> StructuredMatch | None:
    """
    Latest training episodic memory for the athlete.

    Primary: rows with ``event_date``, ORDER BY event_date DESC, created_at DESC.
    Fallback: null event_date (pending) — low confidence only.
    """
    scope = _scope(user_id, session_id)

    stmt = (
        select(Memory)
        .where(scope, _training_clause(), Memory.event_date.isnot(None))
        .order_by(*_order_event_date_created())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalars().first()
    if row:
        return StructuredMatch(row, CONF_LAST_DATED, "structured:last_training:dated")

    fallback = (
        select(Memory)
        .where(scope, _training_clause(), Memory.event_date.is_(None))
        .order_by(Memory.created_at.desc())
        .limit(1)
    )
    pending = (await session.execute(fallback)).scalars().first()
    if pending:
        return StructuredMatch(
            pending,
            CONF_LAST_NULL_DATE_FALLBACK,
            "structured:last_training:pending_date_fallback",
        )
    return None


async def find_last_match(
    session: AsyncSession,
    user_id: str | None,
    *,
    session_id: str = DEFAULT_SESSION_ID,
) -> StructuredMatch | None:
    """Latest match episodic memory — same ordering policy as ``find_last_training``."""
    scope = _scope(user_id, session_id)

    stmt = (
        select(Memory)
        .where(scope, _match_clause(), Memory.event_date.isnot(None))
        .order_by(*_order_event_date_created())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalars().first()
    if row:
        return StructuredMatch(row, CONF_LAST_DATED, "structured:last_match:dated")

    fallback = (
        select(Memory)
        .where(scope, _match_clause(), Memory.event_date.is_(None))
        .order_by(Memory.created_at.desc())
        .limit(1)
    )
    pending = (await session.execute(fallback)).scalars().first()
    if pending:
        return StructuredMatch(
            pending,
            CONF_LAST_NULL_DATE_FALLBACK,
            "structured:last_match:pending_date_fallback",
        )
    return None


async def find_match_by_date(
    session: AsyncSession,
    user_id: str | None,
    target: date,
    *,
    session_id: str = DEFAULT_SESSION_ID,
) -> StructuredMatch | None:
    """Exact calendar day — match_log (or session_type=match) on ``event_date``."""
    scope = _scope(user_id, session_id)
    stmt = (
        select(Memory)
        .where(
            scope,
            Memory.event_date == target,
            or_(Memory.event_type == "match_log", Memory.session_type == SESSION_MATCH),
        )
        .order_by(Memory.created_at.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalars().first()
    if not row:
        return None
    return StructuredMatch(row, CONF_EXACT_DATE, f"structured:match_by_date:{target.isoformat()}")


async def find_training_by_date(
    session: AsyncSession,
    user_id: str | None,
    target: date,
    *,
    session_id: str = DEFAULT_SESSION_ID,
) -> StructuredMatch | None:
    """Exact calendar day — training_log (or session_type=training) on ``event_date``."""
    scope = _scope(user_id, session_id)
    stmt = (
        select(Memory)
        .where(
            scope,
            Memory.event_date == target,
            or_(Memory.event_type == "training_log", Memory.session_type == SESSION_TRAINING),
        )
        .order_by(Memory.created_at.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalars().first()
    if not row:
        return None
    return StructuredMatch(
        row, CONF_EXACT_DATE, f"structured:training_by_date:{target.isoformat()}"
    )


async def find_events_by_date_range(
    session: AsyncSession,
    user_id: str | None,
    start_date: date,
    end_date: date,
    *,
    event_type: str | None = None,
    session_id: str = DEFAULT_SESSION_ID,
) -> list[StructuredMatch]:
    """
    Memories whose ``event_date`` falls in [start_date, end_date] (inclusive).

    Optional ``event_type`` filter (e.g. ``match_log``, ``training_log``).
    When omitted, returns both match and training episodic rows.
    """
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    scope = _scope(user_id, session_id)
    filters = [
        scope,
        Memory.event_date.isnot(None),
        Memory.event_date >= start_date,
        Memory.event_date <= end_date,
    ]
    if event_type:
        filters.append(Memory.event_type == event_type)
    else:
        filters.append(or_(_match_clause(), _training_clause()))

    stmt = (
        select(Memory)
        .where(and_(*filters))
        .order_by(*_order_event_date_created())
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return [
        StructuredMatch(
            m,
            CONF_DATE_RANGE,
            f"structured:date_range:{start_date.isoformat()}..{end_date.isoformat()}",
        )
        for m in rows
    ]


async def find_match_by_day_month(
    session: AsyncSession,
    user_id: str | None,
    day: int,
    month: int,
    reference: date,
    *,
    session_id: str = DEFAULT_SESSION_ID,
) -> StructuredMatch | None:
    """Resolve day/month without year — try reference year downward."""
    years = [reference.year, reference.year - 1, reference.year - 2]
    for year in years:
        try:
            target = date(year, month, day)
        except ValueError:
            continue
        hit = await find_match_by_date(
            session, user_id, target, session_id=session_id
        )
        if hit:
            hit.match_reason = f"structured:match_day_month:{target.isoformat()}"
            hit.confidence = CONF_DAY_MONTH
            return hit
    return None


async def find_by_opponent(
    session: AsyncSession,
    user_id: str | None,
    opponent: str,
    *,
    session_id: str = DEFAULT_SESSION_ID,
) -> StructuredMatch | None:
    pattern = f"%{opponent.lower()}%"
    stmt = (
        select(Memory)
        .where(
            _scope(user_id, session_id),
            or_(
                Memory.value.ilike(pattern),
                Memory.raw_user_text.ilike(pattern),
            ),
            _match_clause(),
            Memory.event_date.isnot(None),
        )
        .order_by(*_order_event_date_created())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalars().first()
    if not row:
        return None
    return StructuredMatch(row, CONF_OPPONENT, "structured:opponent")


# Backward-compatible aliases -------------------------------------------------

async def find_match_on_calendar_date(
    session: AsyncSession,
    *,
    user_id: str | None,
    session_id: str,
    target: date,
) -> StructuredMatch | None:
    hit = await find_match_by_date(session, user_id, target, session_id=session_id)
    if hit:
        return hit
    # Range overlap (e.g. «на прошлой неделе» stored as event_date..event_date_end)
    scope = _scope(user_id, session_id)
    stmt = (
        select(Memory)
        .where(
            scope,
            Memory.event_date.isnot(None),
            Memory.event_date <= target,
            Memory.event_date_end >= target,
            _match_clause(),
        )
        .order_by(Memory.created_at.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalars().first()
    if row:
        return StructuredMatch(row, CONF_DATE_RANGE, "structured:match_date_in_range")
    return None


def format_grounding_block(
    *,
    reference_label: str,
    memory: Memory,
    header: str = "PAST EVENT GROUNDING",
) -> str:
    facts = memory.facts or {}
    facts_lines = ""
    if facts:
        facts_lines = "Facts (structured):\n" + "\n".join(
            f"- {k}: {v}" for k, v in facts.items() if v
        )
    date_line = ""
    if memory.event_date:
        end = f" — {memory.event_date_end}" if memory.event_date_end else ""
        date_line = f"Event date: {memory.event_date}{end}\n"
    raw = ""
    if memory.raw_user_text:
        raw = f"Raw athlete log:\n{memory.raw_user_text.strip()}\n"
    pending = ""
    if isinstance(facts, dict) and facts.get("pending_unresolved_date"):
        pending = (
            "Note: event date was not fully resolved when saved — treat timeline cautiously.\n"
        )
    return (
        f"{header} (verified in athlete memory — use ONLY these facts):\n"
        f"Reference: {reference_label}\n"
        f"{date_line}"
        f"{pending}"
        f"Summary: {memory.value.strip()}\n"
        f"{raw}"
        f"{facts_lines}\n"
        "Do NOT invent scores, opponents, fatigue, tactics, or errors not stated above."
    )
