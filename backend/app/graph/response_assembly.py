"""Assemble /api/chat payload from LangGraph result (latest analyst, blocked invariants)."""

from __future__ import annotations

import json
from typing import Any

from app.graph.llm import extract_analysis_json, strip_analysis_json_from_text
from app.graph.state_utils import state_dict, state_list, unwrap_overwrite

_BLOCKED_REASONS = frozenset(
    {
        "past_event_not_found",
        "past_event_no_retrieved_memory",
        "pending_event_date_unknown",
        "db_session_unavailable",
        "past_event_guard_unavailable",
    }
)

_FAKE_ANALYSIS_MARKERS = (
    "physical_fatigue",
    "tactical_gap",
    "psychological",
    "technical",
    "физическая усталость",
)


def latest_agent_output(
    outputs: list[dict[str, Any]], agent: str = "analyst"
) -> dict[str, Any] | None:
    matched = [o for o in outputs if o.get("agent") == agent]
    return matched[-1] if matched else None


def trace_indicates_blocked_past_event(trace: dict[str, Any] | None) -> bool:
    if not trace:
        return False
    if trace.get("turn_intent") and trace.get("turn_intent") != "PAST_EVENT_LOOKUP_REQUEST":
        return False
    if trace.get("llm_called") is not False:
        return False
    reason = trace.get("blocked_reason")
    return reason in _BLOCKED_REASONS if reason else True


def assemble_chat_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Build API fields from graph result; never prefer stale first analyst output."""
    outputs = state_list(result, "agent_outputs")
    analyst_out = latest_agent_output(outputs)

    analyst_trace = unwrap_overwrite(result.get("analyst_trace"))
    if not isinstance(analyst_trace, dict):
        analyst_trace = None
    if analyst_out and analyst_out.get("analyst_trace"):
        analyst_trace = analyst_out.get("analyst_trace")
    elif analyst_trace is None and analyst_out:
        analyst_trace = analyst_out.get("analyst_trace")

    final = result.get("final_response") or "Ответ не сформирован."
    analysis: dict[str, Any] | None = None
    comparison_status: str | None = None
    comparison_label: str | None = None
    chat_actions: list[dict[str, str]] = []

    if analyst_out:
        comparison_status = analyst_out.get("comparison_status")
        comparison_label = analyst_out.get("comparison_label")
        chat_actions = list(analyst_out.get("chat_actions") or [])
        llm_called = analyst_out.get("llm_called", True)
        blocked = (
            llm_called is False
            or comparison_status == "not_found"
            or trace_indicates_blocked_past_event(analyst_trace)
        )
        if blocked:
            final = (analyst_out.get("content") or final).strip()
            analysis = None
            comparison_status = "not_found"
        else:
            analysis = analyst_out.get("analysis") or extract_analysis_json(
                analyst_out.get("content", "")
            )
            content = analyst_out.get("content")
            if content:
                final = content

    if analysis:
        final = strip_analysis_json_from_text(final)
        if analysis.get("summary"):
            final = (final or "").strip()
            if len(final) > 280:
                final = final[:280].rsplit(" ", 1)[0] + "…"

    return {
        "message": final,
        "agents_used": result.get("agents_used") or [],
        "requires_confirmation": bool(result.get("requires_human_confirmation")),
        "analysis": analysis,
        "needs_memory": bool(result.get("needs_memory")),
        "interaction_mode": result.get("interaction_mode") or "neutral",
        "memory_citations_count": len(result.get("memory_citations") or []),
        "comparison_status": comparison_status,
        "comparison_label": comparison_label,
        "chat_actions": chat_actions,
        "analyst_trace": analyst_trace,
    }


def enforce_blocked_past_event_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Hard override when guard blocked LLM — ignore stale message/analysis."""
    trace = payload.get("analyst_trace") or {}
    if not trace_indicates_blocked_past_event(trace):
        return payload

    msg = (payload.get("message") or "").strip()
    if trace.get("blocked_reason") == "past_event_not_found" and "не нашёл" not in msg.lower():
        # Prefer honest not-found wording when message was polluted by checkpoint merge.
        msg = (
            "Я не нашёл в памяти тренировку на указанную дату. "
            "Опиши её в этом сообщении или добавь запись в историю."
        )

    payload["message"] = msg
    payload["analysis"] = None
    payload["comparison_status"] = "not_found"
    if payload.get("comparison_label") is None and trace.get("event_date_parsed"):
        payload["comparison_label"] = trace.get("event_date_parsed")
    return payload


def assert_past_event_api_invariant(payload: dict[str, Any]) -> None:
    """Dev/test guard: blocked past-event must not leak LLM analysis categories."""
    trace = payload.get("analyst_trace") or {}
    if trace.get("blocked_reason") != "past_event_not_found":
        return
    blob = json.dumps(payload, ensure_ascii=False).lower()
    assert payload.get("analysis") is None, "analysis must be null when past_event_not_found"
    assert payload.get("comparison_status") == "not_found", (
        "comparison_status must be not_found"
    )
    for marker in _FAKE_ANALYSIS_MARKERS:
        assert marker not in blob, f"blocked response must not contain {marker!r}"
