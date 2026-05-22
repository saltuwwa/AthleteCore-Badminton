"""Hybrid retrieval for SQLite MVP: cosine ANN in Python + keyword FTS + RRF + rerank."""

from __future__ import annotations

import re
import uuid
from collections import defaultdict

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings

from .models import Memory, MemoryLayer, Turn
from .recall_gating import cosine_similarity


def memory_scope_clause(user_id: str | None, session_id: str):
    if user_id is not None:
        return Memory.user_id == user_id
    return and_(Memory.user_id.is_(None), Memory.source_session == session_id)


_rr_model = None


def _get_cross_encoder(settings: Settings):
    global _rr_model
    if settings.disable_reranker:
        return None
    if _rr_model is None:
        from sentence_transformers import CrossEncoder

        _rr_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _rr_model


def _keyword_fts_score(query: str, memory: Memory) -> float:
    words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2]
    if not words:
        return 0.0
    blob = f"{memory.key} {memory.value}".lower()
    hits = sum(1 for w in words if w in blob)
    return hits / len(words)


async def hybrid_search(
    session: AsyncSession,
    settings: Settings,
    *,
    query: str,
    user_id: str | None,
    session_id: str,
    limit: int,
    query_embedding: list[float],
) -> list[tuple[Memory, float]]:
    scope = and_(Memory.active.is_(True), memory_scope_clause(user_id, session_id))
    stmt = select(Memory).where(scope)
    all_rows = list((await session.execute(stmt)).scalars().all())

    vec_scored: list[tuple[Memory, float]] = []
    for m in all_rows:
        if not m.embedding:
            continue
        vec_scored.append((m, cosine_similarity(query_embedding, m.embedding)))
    vec_scored.sort(key=lambda x: x[1], reverse=True)
    vec_rows = [m for m, _ in vec_scored[:30]]

    fts_scored = [(m, _keyword_fts_score(query, m)) for m in all_rows]
    fts_scored = [(m, s) for m, s in fts_scored if s > 0]
    fts_scored.sort(key=lambda x: x[1], reverse=True)
    fts_rows = [m for m, _ in fts_scored[:30]]

    vec_ids = [m.id for m in vec_rows]
    fts_ids = [m.id for m in fts_rows]

    k = 60
    rrf: dict[uuid.UUID, float] = defaultdict(float)
    for i, mid in enumerate(vec_ids):
        rrf[mid] += 1.0 / (k + i + 1)
    for i, mid in enumerate(fts_ids):
        rrf[mid] += 1.0 / (k + i + 1)

    if not rrf:
        return []

    mem_map: dict[uuid.UUID, Memory] = {m.id: m for m in vec_rows}
    for m in fts_rows:
        mem_map.setdefault(m.id, m)

    expanded = _extract_entities(query, [mem_map[i] for i in list(rrf.keys())[:10] if i in mem_map])
    if expanded:
        for m in all_rows:
            if m.id in rrf:
                continue
            if any(e.lower() in m.value.lower() for e in expanded[:8]):
                rrf[m.id] = 0.15
                mem_map[m.id] = m

    pool_ids = sorted(rrf.keys(), key=lambda x: rrf[x], reverse=True)[:25]
    pool = [mem_map[i] for i in pool_ids if i in mem_map]

    ce = _get_cross_encoder(settings)
    if ce is not None and pool:
        pairs = [[query, m.value[:2000]] for m in pool]
        scores = ce.predict(pairs)
        order = sorted(range(len(pool)), key=lambda i: scores[i], reverse=True)
        reranked = [pool[i] for i in order]
        score_map = {pool[i].id: float(scores[i]) for i in range(len(pool))}
        return [(m, score_map.get(m.id, rrf.get(m.id, 0.0))) for m in reranked[:limit]]

    reranked = sorted(pool, key=lambda m: rrf[m.id], reverse=True)
    return [(m, float(rrf[m.id])) for m in reranked[:limit]]


def _extract_entities(query: str, memories: list[Memory]) -> list[str]:
    text_blob = query + " " + " ".join(m.value for m in memories)
    caps = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b", text_blob)
    seen: set[str] = set()
    out: list[str] = []
    for c in caps:
        if len(c) < 2 or c.lower() in ("the", "i", "user", "assistant"):
            continue
        if c not in seen:
            seen.add(c)
            out.append(c.strip())
    return out[:12]


async def recent_turn_snippets(
    session: AsyncSession,
    *,
    session_id: str,
    user_id: str | None,
    max_turns: int = 8,
) -> list[tuple[str, str]]:
    q = select(Turn).where(Turn.session_id == session_id)
    if user_id is not None:
        q = q.where(Turn.user_id == user_id)
    q = q.order_by(Turn.created_at.desc()).limit(max_turns)
    rows = list((await session.execute(q)).scalars().all())
    rows.reverse()
    out: list[tuple[str, str]] = []
    for t in rows:
        parts: list[str] = []
        for m in t.messages:
            role = m.get("role", "")
            content = (m.get("content") or "")[:500]
            parts.append(f"{role}: {content}")
        out.append((t.turn_timestamp.isoformat(), "\n".join(parts)))
    return out


async def fetch_high_risk_memories(
    session: AsyncSession,
    *,
    user_id: str | None,
    session_id: str,
) -> list[Memory]:
    from .models import RiskLevel

    scope = and_(Memory.active.is_(True), memory_scope_clause(user_id, session_id))
    stmt = select(Memory).where(scope, Memory.risk_level == RiskLevel.high)
    return list((await session.execute(stmt)).scalars().all())
