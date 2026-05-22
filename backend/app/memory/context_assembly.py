"""Token-bounded context for LangGraph agents (sports sections)."""

from __future__ import annotations

import tiktoken
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ExtractedMemoryType, Memory, MemoryLayer
from .retrieval import memory_scope_clause


def _encoder():
    try:
        return tiktoken.encoding_for_model("gpt-4o")
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoder().encode(text))


def truncate_text_to_token_budget(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    enc = _encoder()
    ids = enc.encode(text)
    if len(ids) <= max_tokens:
        return text
    return enc.decode(ids[:max_tokens])


async def fetch_stable_profile_memories(
    session: AsyncSession,
    *,
    user_id: str | None,
    session_id: str,
    limit: int = 40,
) -> list[Memory]:
    scope = memory_scope_clause(user_id, session_id)
    stmt = (
        select(Memory)
        .where(
            and_(
                Memory.active.is_(True),
                scope,
                or_(
                    Memory.memory_layer == MemoryLayer.semantic,
                    and_(
                        Memory.memory_type == ExtractedMemoryType.preference,
                        Memory.memory_layer != MemoryLayer.episodic,
                    ),
                ),
            )
        )
        .order_by(Memory.importance.desc(), Memory.updated_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def fetch_procedural_memories(
    session: AsyncSession,
    *,
    user_id: str | None,
    session_id: str,
    limit: int = 8,
) -> list[Memory]:
    scope = memory_scope_clause(user_id, session_id)
    stmt = (
        select(Memory)
        .where(
            and_(
                Memory.active.is_(True),
                scope,
                Memory.memory_layer == MemoryLayer.procedural,
            )
        )
        .order_by(Memory.updated_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


def build_recall_context(
    *,
    max_tokens: int,
    stable_rows: list[Memory],
    procedural_rows: list[Memory],
    ranked_memories: list[tuple[Memory, float]],
    recent_lines: list[tuple[str, str]],
) -> tuple[str, list[tuple[str, str, float, str | None]]]:
    profile_lines = [f"- ({m.memory_type.value}) {m.value}" for m in stable_rows]
    proc_lines = [f"- {m.value}" for m in procedural_rows]

    seen_values = {m.value.strip().lower() for m in stable_rows + procedural_rows}
    rel_lines: list[str] = []
    citations: list[tuple[str, str, float, str | None]] = []

    for m, score in ranked_memories:
        key = m.value.strip().lower()
        if key in seen_values:
            continue
        seen_values.add(key)
        layer = m.memory_layer.value
        tag = f"[{layer}]"
        if m.event_type:
            tag = f"[{m.event_type}]"
        rel_lines.append(f"- {tag} {m.value}")
        citations.append((str(m.source_turn_id), m.value[:240], float(score), layer))

    recent_fmt = [f"- [{ts}] {blob}" for ts, blob in recent_lines]

    sections: list[tuple[str, list[str]]] = [
        ("## Athlete profile (stable)", profile_lines),
        ("## Agent interaction rules", proc_lines),
        ("## Relevant training & match memories", rel_lines),
        ("## Recent session", recent_fmt),
    ]

    def render(mask: tuple[bool, bool, bool, bool]) -> str:
        parts: list[str] = []
        for i, (title, lines) in enumerate(sections):
            if mask[i] and lines:
                parts.append(title + "\n" + "\n".join(lines))
        return "\n\n".join(parts)

    mask = (True, True, True, True)
    text = render(mask)
    if count_tokens(text) <= max_tokens:
        return text, citations

    for drop_recent in (True, False):
        mask = (True, True, True, not drop_recent)
        text = render(mask)
        if count_tokens(text) <= max_tokens:
            return text, citations

    mask = (True, True, False, False)
    text = render(mask)
    if count_tokens(text) > max_tokens:
        text = truncate_text_to_token_budget(text, max_tokens)
    return text, citations
