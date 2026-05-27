from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.graph.build import get_compiled_graph
from app.graph.llm import extract_analysis_json, strip_analysis_json_from_text
from app.graph.state import AthleteGraphState
from app.memory.embeddings import embed_texts, openai_client
from app.memory.extraction import extract_memories_from_turn
from app.memory.models import Turn
from app.memory.supersession import apply_supersession_and_insert
from app.memory.write_gate import MemoryWriteGate

_write_gate = MemoryWriteGate()


async def run_chat_graph(
    db: AsyncSession,
    *,
    message: str,
    user_id: str,
    session_id: str,
    thread_id: str | None = None,
) -> dict[str, Any]:
    if not settings.openai_api_key and not settings.anthropic_api_key:
        return {
            "message": (
                "Настрой OPENAI_API_KEY или ANTHROPIC_API_KEY в backend/.env "
                "для работы агентов."
            ),
            "thread_id": thread_id or str(uuid.uuid4()),
            "agents_used": [],
            "requires_confirmation": False,
            "analysis": None,
        }

    tid = thread_id or str(uuid.uuid4())
    graph = await get_compiled_graph()

    config = {
        "configurable": {
            "thread_id": tid,
            "db_session": db,
        }
    }

    prior_offer: str | None = None
    try:
        snap = await graph.aget_state(config)
        if snap and snap.values:
            prior_offer = snap.values.get("offer_followup")
    except Exception:
        prior_offer = None

    initial: AthleteGraphState = {
        "thread_id": tid,
        "user_id": user_id,
        "session_id": session_id,
        "user_input": message,
        "agent_outputs": [],
        "agents_used": [],
        "requires_human_confirmation": False,
        "offer_followup": prior_offer,
    }

    result = await graph.ainvoke(initial, config)

    final = result.get("final_response") or "Ответ не сформирован."
    agents_used = result.get("agents_used") or []
    outputs = result.get("agent_outputs") or []
    analysis = None
    for out in outputs:
        if out.get("agent") == "analyst":
            analysis = out.get("analysis") or extract_analysis_json(out.get("content", ""))
            break

    if analysis:
        final = strip_analysis_json_from_text(final)

    needs_memory = bool(result.get("needs_memory"))
    interaction_mode = result.get("interaction_mode") or "neutral"
    offer_followup = result.get("offer_followup")

    if needs_memory:
        await _persist_turn_memories(
            db,
            user_id=user_id,
            session_id=session_id,
            user_message=message,
            assistant_message=final,
        )

    await _persist_interaction_offer(
        db,
        user_id=user_id,
        session_id=session_id,
        offer=offer_followup,
        interaction_mode=interaction_mode,
    )

    return {
        "message": final,
        "thread_id": tid,
        "agents_used": agents_used,
        "requires_confirmation": bool(result.get("requires_human_confirmation")),
        "analysis": analysis,
        "needs_memory": needs_memory,
        "interaction_mode": interaction_mode,
        "memory_citations_count": len(result.get("memory_citations") or []),
    }


async def _persist_turn_memories(
    db: AsyncSession,
    *,
    user_id: str,
    session_id: str,
    user_message: str,
    assistant_message: str,
) -> None:
    """Cold-path: store chat turn + extract LTM (when OpenAI key present)."""
    if not settings.openai_api_key:
        return

    turn = Turn(
        session_id=session_id,
        user_id=user_id,
        messages=[
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_message[:4000]},
        ],
        turn_timestamp=datetime.now(UTC),
        metadata_={"source": "api_chat"},
    )
    db.add(turn)
    await db.flush()

    try:
        client = openai_client(settings)
        candidates = await extract_memories_from_turn(
            client, settings, turn.messages
        )
        candidates = _write_gate.filter_candidates(candidates)
        if not candidates:
            await db.commit()
            return

        texts = [f"{c['key']}: {c['value']}" for c in candidates]
        embeddings = await embed_texts(
            client,
            settings.embedding_model,
            texts,
            dimensions=settings.embedding_dimensions,
        )
        await apply_supersession_and_insert(
            db,
            user_id=user_id,
            source_session=session_id,
            source_turn_id=turn.id,
            candidates=candidates,
            embeddings=embeddings,
        )
        await db.commit()
    except Exception:
        await db.rollback()


async def _persist_interaction_offer(
    db: AsyncSession,
    *,
    user_id: str,
    session_id: str,
    offer: str | None,
    interaction_mode: str,
) -> None:
    """Store pending analysis consent (HITL) or clear after full debrief."""
    if not settings.openai_api_key:
        return
    from app.memory.mapping import normalize_candidate

    if interaction_mode == "full_analysis":
        value = "none — debrief completed"
    elif offer:
        value = f"{offer} — awaiting athlete yes/no"
    else:
        return

    try:
        client = openai_client(settings)
        candidate = normalize_candidate(
            {
                "type": "preference",
                "key": "interaction.pending_offer",
                "value": value,
                "confidence": 0.95,
                "supersedes_same_key": True,
                "importance": 0.85,
            }
        )
        emb = await embed_texts(
            client,
            settings.embedding_model,
            [f"{candidate['key']}: {candidate['value']}"],
            dimensions=settings.embedding_dimensions,
        )
        turn_stub = Turn(
            session_id=session_id,
            user_id=user_id,
            messages=[],
            turn_timestamp=datetime.now(UTC),
            metadata_={"source": "interaction_offer"},
        )
        db.add(turn_stub)
        await db.flush()
        await apply_supersession_and_insert(
            db,
            user_id=user_id,
            source_session=session_id,
            source_turn_id=turn_stub.id,
            candidates=[candidate],
            embeddings=emb,
        )
        await db.commit()
    except Exception:
        await db.rollback()
