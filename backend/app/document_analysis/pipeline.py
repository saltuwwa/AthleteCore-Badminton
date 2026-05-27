from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.document_analysis.analysis import analyze_document_safe
from app.document_analysis.entity_parser import parse_sports_entities
from app.document_analysis.extraction import extract_text
from app.document_analysis.schemas import (
    DocumentAction,
    DocumentAnalyzeResponse,
    StructuredCompetitionData,
)
from app.memory.document_memory_service import persist_competition_document_memory
from app.memory.models import Memory
from app.security.untrusted_content import redact_injection_content, sanitize_untrusted_text


async def _past_tournament_context(session: AsyncSession, user_id: str) -> str:
    stmt = (
        select(Memory)
        .where(
            Memory.user_id == user_id,
            Memory.active.is_(True),
            Memory.event_type == "competition_document_analysis",
        )
        .order_by(Memory.created_at.desc())
        .limit(5)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    if not rows:
        return ""
    lines = ["Past competition analyses (structured summaries only):"]
    for r in rows:
        p = r.payload or {}
        lines.append(
            f"- {p.get('tournament_name')} {p.get('date')}: "
            f"{len(p.get('match_list') or [])} matches"
        )
    return "\n".join(lines)


async def run_document_analysis(
    session: AsyncSession,
    *,
    document_id: str,
    user_id: str,
    action: DocumentAction,
    athlete_name: str | None = None,
) -> DocumentAnalyzeResponse:
    raw_text, dtype = extract_text(document_id)
    sanitized = sanitize_untrusted_text(raw_text)
    injection = redact_injection_content(sanitized)
    safe_text = injection.redacted_text

    structured = parse_sports_entities(safe_text, injection)
    memory_ctx = await _past_tournament_context(session, user_id)

    structured, assistant_msg = analyze_document_safe(
        action=action,
        structured=structured,
        safe_excerpt=safe_text,
        athlete_name=athlete_name,
        memory_context=memory_ctx,
    )

    saved = await persist_competition_document_memory(
        session,
        user_id=user_id,
        document_id=document_id,
        structured=structured,
    )

    return DocumentAnalyzeResponse(
        document_id=document_id,
        action=action,
        detected_type=dtype,
        structured=structured,
        assistant_message=assistant_msg,
        memory_saved=saved,
    )
