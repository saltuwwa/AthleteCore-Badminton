import uuid
from datetime import date, datetime, timezone

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .constants import DEFAULT_SPORT, MEMORY_SCHEMA_VERSION
from .mapping import parse_risk_level
from .models import ExtractedMemoryType, Memory, MemoryLayer


def _coerce_memory_type(raw: str) -> ExtractedMemoryType:
    try:
        return ExtractedMemoryType(raw)
    except ValueError:
        return ExtractedMemoryType.fact


def _coerce_layer(raw: str) -> MemoryLayer:
    try:
        return MemoryLayer(raw)
    except ValueError:
        return MemoryLayer.semantic


def _coerce_date(raw) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, date):
        return raw
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, str) and raw.strip():
        try:
            parts = raw.strip()[:10].split("-")
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, IndexError):
            return None
    return None


def _same_slot_clause(user_id: str | None, source_session: str, key: str):
    key_match = Memory.key == key
    active = Memory.active.is_(True)
    if user_id is None:
        return and_(
            Memory.user_id.is_(None),
            Memory.source_session == source_session,
            key_match,
            active,
        )
    return and_(Memory.user_id == user_id, key_match, active)


async def apply_supersession_and_insert(
    session: AsyncSession,
    *,
    user_id: str | None,
    source_session: str,
    source_turn_id: uuid.UUID,
    candidates: list[dict],
    embeddings: list[list[float]],
) -> list[Memory]:
    created: list[Memory] = []
    if len(embeddings) != len(candidates):
        raise ValueError("embeddings length must match candidates")

    for cand, emb in zip(candidates, embeddings, strict=True):
        key = cand["key"]
        stmt = (
            select(Memory)
            .where(_same_slot_clause(user_id, source_session, key))
            .order_by(Memory.updated_at.desc())
        )
        prev_rows = list((await session.execute(stmt)).scalars().all())

        supersedes_id: uuid.UUID | None = None
        if prev_rows:
            supersedes_id = prev_rows[0].id
            await session.execute(
                update(Memory)
                .where(_same_slot_clause(user_id, source_session, key))
                .values(active=False, updated_at=datetime.now(timezone.utc))
            )

        facts = cand.get("facts")
        if not isinstance(facts, dict):
            facts = None

        row = Memory(
            user_id=user_id,
            source_session=source_session,
            source_turn_id=source_turn_id,
            memory_type=_coerce_memory_type(cand["type"]),
            memory_layer=_coerce_layer(cand["memory_layer"]),
            key=key,
            value=cand["value"],
            confidence=float(cand.get("confidence", 0.8)),
            importance=float(cand.get("importance", 0.5)),
            event_type=cand.get("event_type"),
            risk_level=parse_risk_level(cand.get("risk_level")),
            payload=cand.get("payload") or {},
            event_date=_coerce_date(cand.get("event_date")),
            event_date_end=_coerce_date(cand.get("event_date_end")),
            raw_user_text=cand.get("raw_user_text"),
            source=cand.get("source"),
            sport=cand.get("sport") or DEFAULT_SPORT,
            session_type=cand.get("session_type"),
            facts=facts,
            schema_version=int(cand.get("schema_version") or MEMORY_SCHEMA_VERSION),
            embedding=emb,
            supersedes_id=supersedes_id,
            active=True,
        )
        session.add(row)
        created.append(row)

    await session.flush()
    return created
