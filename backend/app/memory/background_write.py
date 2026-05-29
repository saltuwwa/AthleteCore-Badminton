"""Schedule LTM extraction/embedding after chat response (non-blocking)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.graph.runner import _persist_turn_memories
from app.memory.pending_write import clear_pending, register_pending

logger = logging.getLogger(__name__)


async def run_background_memory_write(
    *,
    user_id: str,
    session_id: str,
    user_message: str,
    assistant_message: str,
    turn_decision: dict[str, Any] | None = None,
    parent_request_id: str | None = None,
) -> None:
    from app.observability.langfuse_tracing import (
        finish_background_trace,
        langfuse_observation_span,
        start_linked_background_trace,
    )

    lf_ctx = None
    if parent_request_id:
        lf_ctx = start_linked_background_trace(
            parent_request_id=parent_request_id,
            user_id=user_id,
            session_id=session_id,
        )
    status = "success"
    try:
        with langfuse_observation_span(
            "memory_write_background",
            metadata={"parent_request_id": parent_request_id},
        ):
            async with AsyncSessionLocal() as db:
                await _persist_turn_memories(
                    db,
                    user_id=user_id,
                    session_id=session_id,
                    user_message=user_message,
                    assistant_message=assistant_message,
                )
    except Exception:
        status = "error"
        logger.exception(
            "background memory_write failed user_id=%s session_id=%s",
            user_id,
            session_id,
        )
    finally:
        finish_background_trace(lf_ctx, status=status)
        await clear_pending(user_id=user_id, session_id=session_id)


async def prepare_pending_memory_write(
    *,
    user_id: str,
    session_id: str,
    user_message: str,
    assistant_message: str,
    turn_decision: dict[str, Any] | None = None,
) -> None:
    turn = turn_decision or {}
    await register_pending(
        user_id=user_id,
        session_id=session_id,
        user_message=user_message,
        assistant_message=assistant_message,
        event_date=turn.get("event_date"),
        inline_facts_summary=str(turn.get("inline_facts_summary") or ""),
        event_type=turn.get("event_type"),
    )


def schedule_memory_write(
    background_tasks: BackgroundTasks,
    *,
    user_id: str,
    session_id: str,
    user_message: str,
    assistant_message: str,
    turn_decision: dict[str, Any] | None = None,
    parent_request_id: str | None = None,
) -> None:
    background_tasks.add_task(
        run_background_memory_write,
        user_id=user_id,
        session_id=session_id,
        user_message=user_message,
        assistant_message=assistant_message,
        turn_decision=turn_decision,
        parent_request_id=parent_request_id,
    )
