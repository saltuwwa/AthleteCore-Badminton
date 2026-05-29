"""Inject MCP tool outputs into LangGraph specialist prompts."""

from __future__ import annotations

from app.graph.latency_trace import current_latency_trace, stage_span
from app.graph.methodology_gate import needs_methodology_rag
from app.mcp_tools.methodology import format_methodology_context, search_sports_methodology
from app.mcp_tools.schedule import format_schedule_context, get_training_schedule


async def build_analyst_context(
    user_input: str,
    memory_context: str,
    *,
    turn_decision: dict | None = None,
    past_event_found: bool = False,
) -> str:
    turn = turn_decision or {}
    use_rag, skip_reason = needs_methodology_rag(
        user_input,
        turn_intent=turn.get("turn_intent"),
        past_event_found=past_event_found,
    )
    trace = current_latency_trace()
    if trace and skip_reason:
        trace.set_meta("methodology_rag_skipped_reason", skip_reason)
    hits: list[dict] = []
    if use_rag:
        with stage_span("methodology_rag"):
            hits = search_sports_methodology(user_input, top_k=4)
    meth = format_methodology_context(hits)
    parts = [memory_context.strip()] if memory_context else []
    if meth:
        parts.append(meth)
    return "\n\n".join(parts).strip()


async def build_scheduler_context(user_input: str, memory_context: str, user_id: str) -> str:
    cal = await get_training_schedule(user_id=user_id)
    cal_text = format_schedule_context(cal)
    parts = [memory_context.strip()] if memory_context else []
    parts.append(cal_text)
    parts.append(
        "If you recommend a new block, describe it clearly (date, time, title, type). "
        "The system may register it as pending_confirmation for HITL."
    )
    return "\n\n".join(p(parts) for p in parts if p).strip()
