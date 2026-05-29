"""AthleteCore API — memory (LTM) + LangGraph multi-agent chat."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from openai import APIError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_optional_auth
from app.config import settings
from app.database import dispose_engine, get_session, init_db, skip_db_init
from app.memory.embeddings import embed_texts, openai_client
from app.memory.extraction import extract_memories_from_turn
from app.memory.models import Memory, Turn
from app.memory.service import MemoryContextService
from app.memory.supersession import apply_supersession_and_insert
from app.memory.write_gate import MemoryWriteGate
from app.graph.build import init_graph_runtime, shutdown_graph_runtime
from app.graph.match_comparison import build_suggestions_from_memories, fetch_event_memories
from app.graph.runner import run_chat_graph
from app.schemas import (
    ChatResponse,
    ChatSuggestionsOut,
    MemoriesListOut,
    MemoryOut,
    RecallIn,
    RecallOut,
    SearchIn,
    SearchOut,
    SearchResultItem,
    TranscribeResponse,
    TurnCreated,
    TurnIn,
)
from app.schedule.service import ScheduleService
from app.transcription import transcribe_audio_bytes
from app.document_analysis import router as document_analysis_router
from video_analysis.routes import router as video_analysis_router

memory_service = MemoryContextService()
write_gate = MemoryWriteGate()
schedule_service = ScheduleService()


def _rows_to_memory_outs(rows: list[Memory]) -> list[MemoryOut]:
    return [
        MemoryOut(
            id=str(m.id),
            user_id=m.user_id,
            type=m.memory_type.value,
            layer=m.memory_layer.value,
            key=m.key,
            value=m.value,
            confidence=m.confidence,
            importance=m.importance,
            event_type=m.event_type,
            risk_level=m.risk_level.value if m.risk_level else None,
            source_session=m.source_session,
            source_turn=str(m.source_turn_id),
            created_at=m.created_at,
            updated_at=m.updated_at,
            supersedes=str(m.supersedes_id) if m.supersedes_id else None,
            active=m.active,
            event_date=m.event_date,
            event_date_end=m.event_date_end,
            raw_user_text=m.raw_user_text,
            source=m.source,
            sport=m.sport,
            session_type=m.session_type,
            facts=m.facts,
            schema_version=m.schema_version,
        )
        for m in rows
    ]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not skip_db_init():
        await init_db()
    await init_graph_runtime()
    yield
    await shutdown_graph_runtime()
    if not skip_db_init():
        await dispose_engine()


app = FastAPI(title="AthleteCore Backend", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(video_analysis_router)
app.include_router(document_analysis_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "AthleteCore", "docs": "/docs", "health": "/health"}


@app.get("/health")
async def health() -> dict[str, str | bool | int]:
    rag_mode = "lexical"
    rag_points = 0
    if settings.methodology_use_qdrant:
        try:
            from app.rag.retrieve import qdrant_available
            from app.rag.qdrant_store import collection_point_count, make_client

            if qdrant_available():
                rag_mode = "qdrant"
                rag_points = collection_point_count(
                    make_client(settings), settings.qdrant_collection_methodology
                )
        except Exception:
            rag_mode = "lexical"
    return {
        "status": "ok",
        "whisper_configured": bool(settings.openai_api_key),
        "methodology_rag": rag_mode,
        "methodology_vectors": rag_points,
    }


@app.post("/api/transcribe", response_model=TranscribeResponse)
async def api_transcribe(audio: UploadFile = File(...)):
    """Voice log → text via OpenAI Whisper (browser MediaRecorder webm/opus)."""
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty audio file")

    try:
        text, duration = await transcribe_audio_bytes(
            raw,
            filename=audio.filename or "recording.webm",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Whisper API error: {e!s}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e!s}") from e

    if not text:
        raise HTTPException(status_code=422, detail="Could not transcribe audio")

    return TranscribeResponse(
        text=text,
        duration_sec=duration,
        language=settings.whisper_language,
    )


@app.get("/api/chat/suggestions", response_model=ChatSuggestionsOut)
async def api_chat_suggestions(
    user_id: str = Query("aigerim"),
    session_id: str = Query("main"),
    session: AsyncSession = Depends(get_session),
):
    """Input chips grounded in real match/training memories (no fake dates)."""
    memories = await fetch_event_memories(
        session, user_id=user_id, session_id=session_id, limit=40
    )
    return ChatSuggestionsOut(suggestions=build_suggestions_from_memories(memories))


@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(
    background_tasks: BackgroundTasks,
    message: str = Form(...),
    user_id: str = Form("aigerim"),
    session_id: str = Form("main"),
    thread_id: str | None = Form(None),
    image: UploadFile | None = File(None),
    session: AsyncSession = Depends(get_session),
):
    """
    Main chat endpoint for frontend (LangGraph pipeline).

    Flow: load LTM memory → Planner route → Specialist → Aggregator → persist turn.
    """
    if image is not None:
        await image.read()  # Vision stub — wired in a later iteration

    from app.graph.latency_trace import (
        clear_latency_trace,
        init_latency_trace,
        log_latency_summary,
        stage_span,
    )

    from app.observability.langfuse_tracing import (
        clear_langfuse_context,
        finish_api_chat_trace,
        record_langfuse_exception,
        start_api_chat_trace,
    )

    trace = init_latency_trace()
    start_api_chat_trace(
        request_id=trace.request_id,
        user_id=user_id,
        session_id=session_id,
        thread_id=thread_id,
        message=message.strip(),
    )
    try:
        with stage_span("request_received"):
            print(
                f"[api/chat] build=semantic-router-v1 "
                f"development_mode={settings.development_mode} user_id={user_id!r}"
            )
            result = await run_chat_graph(
                session,
                message=message.strip(),
                user_id=user_id,
                session_id=session_id,
                thread_id=thread_id,
            )
        if result.get("memory_write_scheduled") and result.get("memory_write_payload"):
            from app.memory.background_write import (
                prepare_pending_memory_write,
                schedule_memory_write,
            )

            payload = result.pop("memory_write_payload", None)
            result.pop("memory_write_scheduled", None)
            if payload:
                parent_rid = trace.request_id
                await prepare_pending_memory_write(**payload)
                trace.set_meta("memory_write_mode", "background")
                trace.set_meta("memory_write_scheduled", True)
                schedule_memory_write(
                    background_tasks,
                    parent_request_id=parent_rid,
                    **payload,
                )

        trace.finish()
        lf_refs = finish_api_chat_trace(
            result=result,
            latency_meta=trace.meta,
            total_latency_ms=trace.total_ms,
        )
        if settings.development_mode:
            result["latency_trace"] = trace.to_dict()
            if lf_refs.get("langfuse_trace_id"):
                result["langfuse_trace_id"] = lf_refs["langfuse_trace_id"]
                result["langfuse_trace_url"] = lf_refs.get("langfuse_trace_url")
        log_latency_summary(trace)
        return ChatResponse(**result)
    except Exception as e:
        trace.finish()
        record_langfuse_exception(e, stage="api_chat")
        finish_api_chat_trace(
            result={"message": "", "thread_id": thread_id or "", "agents_used": []},
            latency_meta=trace.meta,
            total_latency_ms=trace.total_ms,
        )
        log_latency_summary(trace)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e!s}") from e
    finally:
        clear_latency_trace()
        clear_langfuse_context()


@app.get("/api/schedule/events")
async def api_schedule_events(
    user_id: str = Query("aigerim"),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Calendar for UI / MCP — same data as get_training_schedule tool."""
    rows = await schedule_service.list_events(
        session,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
    )
    return {
        "events": [
            {
                "id": e.id,
                "date": e.event_date,
                "startTime": e.start_time,
                "endTime": e.end_time,
                "title": e.title,
                "type": e.event_type,
                "intensity": e.intensity,
                "aiAdded": e.ai_added,
                "status": e.status,
            }
            for e in rows
        ]
    }


@app.post("/turns", response_model=TurnCreated, status_code=201, dependencies=[Depends(verify_optional_auth)])
async def post_turn(
    body: TurnIn,
    session: AsyncSession = Depends(get_session),
):
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    msgs = [m.model_dump(exclude_none=True) for m in body.messages]
    turn = Turn(
        session_id=body.session_id,
        user_id=body.user_id,
        messages=msgs,
        turn_timestamp=body.timestamp,
        metadata_=body.metadata or {},
    )
    session.add(turn)
    await session.flush()

    try:
        client = openai_client(settings)
        from app.memory.extraction import concat_user_text, extract_memories_from_turn
        from app.memory.write_enrichment import enrich_candidates_for_turn

        user_text = concat_user_text(msgs)
        candidates = await extract_memories_from_turn(
            client, settings, msgs, reference_date=turn.turn_timestamp
        )
        candidates = enrich_candidates_for_turn(
            candidates,
            raw_user_text=user_text,
            turn_timestamp=turn.turn_timestamp,
            timezone=settings.memory_timezone,
        )
        candidates = write_gate.filter_candidates(candidates, raw_user_text=user_text)

        embeddings: list[list[float]] = []
        if candidates:
            texts = [f"{c['key']}: {c['value']}" for c in candidates]
            embeddings = await embed_texts(
                client,
                settings.embedding_model,
                texts,
                dimensions=settings.embedding_dimensions,
            )

        written = await apply_supersession_and_insert(
            session,
            user_id=body.user_id,
            source_session=body.session_id,
            source_turn_id=turn.id,
            candidates=candidates,
            embeddings=embeddings,
        )
        await session.commit()
    except APIError as e:
        await session.rollback()
        raise HTTPException(status_code=502, detail=f"OpenAI API error: {e!s}") from e
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e!s}") from e

    return TurnCreated(id=str(turn.id), memories_written=len(written))


@app.post("/recall", response_model=RecallOut, dependencies=[Depends(verify_optional_auth)])
async def post_recall(
    body: RecallIn,
    session: AsyncSession = Depends(get_session),
):
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")
    return await memory_service.recall_http(
        session,
        query=body.query,
        session_id=body.session_id,
        user_id=body.user_id,
        max_tokens=body.max_tokens,
    )


@app.post("/search", response_model=SearchOut, dependencies=[Depends(verify_optional_auth)])
async def post_search(
    body: SearchIn,
    session: AsyncSession = Depends(get_session),
):
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    from app.memory.embeddings import embed_query
    from app.memory.recall_gating import gate_ranked_memories
    from app.memory.retrieval import hybrid_search

    if body.user_id is None and not body.session_id:
        raise HTTPException(status_code=400, detail="Provide session_id or user_id")

    client = openai_client(settings)
    sid = body.session_id or ""
    q_emb = await embed_query(
        client,
        settings.embedding_model,
        body.query,
        dimensions=settings.embedding_dimensions,
    )
    ranked = await hybrid_search(
        session,
        settings,
        query=body.query,
        user_id=body.user_id,
        session_id=sid,
        limit=max(1, min(body.limit, 50)),
        query_embedding=q_emb,
    )
    ranked = gate_ranked_memories(q_emb, ranked, settings.recall_ranked_min_cos)

    results: list[SearchResultItem] = []
    for m, score in ranked:
        t_row = await session.get(Turn, m.source_turn_id)
        ts = t_row.turn_timestamp if t_row else datetime.now(UTC)
        meta = (t_row.metadata_ if t_row else {}) or {}
        results.append(
            SearchResultItem(
                content=f"{m.key}: {m.value}",
                score=score,
                session_id=m.source_session,
                timestamp=ts,
                metadata=meta,
                user_id=m.user_id,
                memory_layer=m.memory_layer.value,
            )
        )
    return SearchOut(results=results)


@app.get("/users/{user_id}/memories", response_model=MemoriesListOut, dependencies=[Depends(verify_optional_auth)])
async def get_user_memories(user_id: str, session: AsyncSession = Depends(get_session)):
    stmt = select(Memory).where(Memory.user_id == user_id).order_by(Memory.updated_at.desc())
    rows = list((await session.execute(stmt)).scalars().all())
    return MemoriesListOut(memories=_rows_to_memory_outs(rows))


@app.delete("/sessions/{session_id}", status_code=204, dependencies=[Depends(verify_optional_auth)])
async def delete_session(session_id: str, session: AsyncSession = Depends(get_session)):
    await session.execute(delete(Turn).where(Turn.session_id == session_id))
    await session.commit()
    return Response(status_code=204)


@app.delete("/users/{user_id}", status_code=204, dependencies=[Depends(verify_optional_auth)])
async def delete_user(user_id: str, session: AsyncSession = Depends(get_session)):
    await session.execute(delete(Turn).where(Turn.user_id == user_id))
    await session.commit()
    return Response(status_code=204)
