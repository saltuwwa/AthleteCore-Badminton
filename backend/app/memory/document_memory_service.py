from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.document_analysis.schemas import StructuredCompetitionData
from app.memory.embeddings import embed_texts, openai_client
from app.memory.models import Turn
from app.memory.supersession import apply_supersession_and_insert
from app.memory.write_gate import MemoryWriteGate

_write_gate = MemoryWriteGate()


def build_competition_memory_payload(
    *,
    user_id: str,
    document_id: str,
    structured: StructuredCompetitionData,
) -> dict[str, Any]:
    """Episodic payload — structured sports data only, no raw document text."""
    return {
        "user_id": user_id,
        "source_document_id": document_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "tournament_name": structured.tournament_name,
        "date": structured.date,
        "match_list": [m.model_dump(mode="json") for m in structured.match_list[:50]],
        "scores": structured.scores[:30],
        "rounds": structured.rounds[:20],
        "player_results": structured.player_results[:30],
        "insights": structured.insights[:15],
        "recommendations": structured.recommendations[:10],
        "security_flag": structured.security_flag,
    }


def payload_to_memory_candidate(
    payload: dict[str, Any],
    document_id: str,
) -> dict[str, Any]:
    summary = (
        f"Tournament doc: {payload.get('tournament_name') or 'unknown'} "
        f"({len(payload.get('match_list') or [])} matches)"
    )
    return {
        "type": "event",
        "key": f"competition.document.{document_id}",
        "value": summary[:500],
        "confidence": 0.9,
        "supersedes_same_key": True,
        "memory_layer": "episodic",
        "event_type": "competition_document_analysis",
        "importance": 0.72,
        "is_repeated_pattern": False,
        "payload": payload,
    }


async def persist_competition_document_memory(
    session: AsyncSession,
    *,
    user_id: str,
    document_id: str,
    structured: StructuredCompetitionData,
    session_id: str | None = None,
) -> bool:
    if structured.security_flag == "prompt_injection_detected":
        # Still save safe structured data; payload excludes raw malicious text by design
        pass

    payload = build_competition_memory_payload(
        user_id=user_id,
        document_id=document_id,
        structured=structured,
    )
    candidate = payload_to_memory_candidate(payload, document_id)
    gated = _write_gate.filter_candidates([candidate])
    if not gated:
        return False

    sid = session_id or f"docs:{user_id}"
    turn = Turn(
        session_id=sid,
        user_id=user_id,
        messages=[{"role": "system", "content": f"competition_document:{document_id}"}],
        turn_timestamp=datetime.now(UTC),
        metadata_={"source": "competition_document_analysis"},
    )
    session.add(turn)
    await session.flush()

    embeddings: list[list[float]] = [[]]
    if settings.openai_api_key:
        client = openai_client(settings)
        embeddings = await embed_texts(
            client,
            settings.embedding_model,
            [f"{candidate['key']}: {candidate['value']}"],
            dimensions=settings.embedding_dimensions,
        )

    await apply_supersession_and_insert(
        session,
        user_id=user_id,
        source_session=sid,
        source_turn_id=turn.id,
        candidates=gated,
        embeddings=embeddings,
    )
    await session.commit()
    return True
