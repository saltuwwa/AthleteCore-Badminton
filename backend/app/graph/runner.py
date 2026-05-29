from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from langgraph.types import Overwrite

from app.config import settings
from app.graph.build import get_compiled_graph
from app.graph.latency_trace import stage_span
from app.graph.response_assembly import (
    assert_past_event_api_invariant,
    assemble_chat_payload,
    enforce_blocked_past_event_response,
)
from app.graph.state import AthleteGraphState
from app.memory.embeddings import embed_texts, openai_client
from app.memory.extraction import concat_user_text, extract_memories_from_turn
from app.memory.write_enrichment import enrich_candidates_for_turn
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

    from app.graph.pending_followup import get_thread_pending_followup

    prior_offer: str | None = None
    prior_pending: dict[str, Any] | None = None
    try:
        snap = await graph.aget_state(config)
        if snap and snap.values:
            prior_offer = snap.values.get("offer_followup")
            prior_pending = snap.values.get("pending_followup")
    except Exception:
        prior_offer = None
        prior_pending = None
    if not prior_pending:
        prior_pending = get_thread_pending_followup(tid)

    # Overwrite only for reducer fields (operator.add). Plain values for dict/scalars —
    # Overwrite({}) is truthy and breaks `state.get("turn_decision") or {}`.
    initial: AthleteGraphState = {
        "thread_id": tid,
        "user_id": user_id,
        "session_id": session_id,
        "user_input": message,
        "agent_outputs": Overwrite([]),  # type: ignore[typeddict-item]
        "agents_used": [],
        "analyst_trace": None,
        "llm_called": False,
        "final_response": "",
        "memory_context": "",
        "memory_citations": [],
        "turn_decision": {},
        "requires_human_confirmation": False,
    }
    # Do not pass None — LangGraph input would wipe checkpointed follow-up state.
    if prior_offer is not None:
        initial["offer_followup"] = prior_offer
    if prior_pending is not None:
        initial["pending_followup"] = prior_pending

    with stage_span("graph_invoke"):
        result = await graph.ainvoke(initial, config)

    with stage_span("response_assembly"):
        assembled = assemble_chat_payload(result)
        assembled = enforce_blocked_past_event_response(assembled)
        assert_past_event_api_invariant(assembled)

    final = assembled["message"]
    needs_memory = assembled["needs_memory"]
    interaction_mode = assembled["interaction_mode"]
    offer_followup = result.get("offer_followup")

    persist_memory = bool(result.get("persist_memory"))
    memory_write_scheduled = False
    memory_write_payload: dict[str, Any] | None = None
    if persist_memory:
        memory_write_scheduled = True
        memory_write_payload = {
            "user_id": user_id,
            "session_id": session_id,
            "user_message": message,
            "assistant_message": final,
            "turn_decision": result.get("turn_decision") or {},
        }

    await _persist_interaction_offer(
        db,
        user_id=user_id,
        session_id=session_id,
        offer=offer_followup,
        interaction_mode=interaction_mode,
    )

    return {
        "thread_id": tid,
        "debug_build_id": "semantic-router-v1",
        "memory_write_scheduled": memory_write_scheduled,
        "memory_write_payload": memory_write_payload,
        **assembled,
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
        user_text = concat_user_text(turn.messages)
        candidates = await extract_memories_from_turn(
            client,
            settings,
            turn.messages,
            reference_date=turn.turn_timestamp,
        )
        candidates = enrich_candidates_for_turn(
            candidates,
            raw_user_text=user_text,
            turn_timestamp=turn.turn_timestamp,
            timezone=settings.memory_timezone,
        )
        candidates = _write_gate.filter_candidates(candidates, raw_user_text=user_text)
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
