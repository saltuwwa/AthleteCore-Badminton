"""Development-mode trace for Analyst turns (memory read path + LLM I/O)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config import Settings
from app.graph.state_utils import state_dict
from app.memory.past_event_guard import PastEventResolution
from app.memory.retrieval_trace import RetrievedMemoryTraceItem, memory_row_to_trace_item


@dataclass(slots=True)
class AnalystTrace:
    user_message: str = ""
    detected_intent: dict[str, Any] = field(default_factory=dict)
    is_past_event_request: bool = False
    memory_query: str = ""
    retrieved_memory_items: list[RetrievedMemoryTraceItem] = field(default_factory=list)
    confidence_score: float | None = None
    similarity_score: float | None = None
    llm_called: bool = False
    structured_retrieval_used: bool = False
    structured_function_called: str | None = None
    semantic_fallback_used: bool = False
    event_date_parsed: str | None = None
    date_normalization_reason: str | None = None
    blocked_reason: str | None = None
    final_prompt_sent_to_llm: dict[str, Any] | None = None
    raw_llm_response: str | None = None
    parsed_json_response: dict[str, Any] | None = None
    inline_facts_in_message: bool = False
    turn_intent: str | None = None
    router_reason: str | None = None
    memory_action: str | None = None
    event_type: str | None = None
    event_date: str | None = None
    recommended_agent: str | None = None
    safety_invariant_applied: str | None = None

    @property
    def retrieved_memory_items_count(self) -> int:
        return len(self.retrieved_memory_items)

    def apply_past_event_invariant(self) -> None:
        if (
            self.is_past_event_request
            and self.retrieved_memory_items_count == 0
            and not self.inline_facts_in_message
        ):
            self.llm_called = False
            if not self.blocked_reason:
                self.blocked_reason = "past_event_no_retrieved_memory"

    def violates_past_event_llm_invariant(self) -> bool:
        return (
            self.is_past_event_request
            and self.retrieved_memory_items_count == 0
            and not self.inline_facts_in_message
            and self.llm_called
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_message": self.user_message,
            "detected_intent": self.detected_intent,
            "is_past_event_request": self.is_past_event_request,
            "memory_query": self.memory_query,
            "retrieved_memory_items": {
                "count": self.retrieved_memory_items_count,
                "items": [i.to_dict() for i in self.retrieved_memory_items],
            },
            "confidence_score": self.confidence_score,
            "similarity_score": self.similarity_score,
            "llm_called": self.llm_called,
            "structured_retrieval_used": self.structured_retrieval_used,
            "structured_function_called": self.structured_function_called,
            "semantic_fallback_used": self.semantic_fallback_used,
            "event_date_parsed": self.event_date_parsed,
            "date_normalization_reason": self.date_normalization_reason,
            "blocked_reason": self.blocked_reason,
            "final_prompt_sent_to_llm": self.final_prompt_sent_to_llm,
            "raw_llm_response": self.raw_llm_response,
            "parsed_json_response": self.parsed_json_response,
            "inline_facts_in_message": self.inline_facts_in_message,
            "turn_intent": self.turn_intent,
            "router_reason": self.router_reason,
            "memory_action": self.memory_action,
            "event_type": self.event_type,
            "event_date": self.event_date,
            "recommended_agent": self.recommended_agent,
            "safety_invariant_applied": self.safety_invariant_applied,
        }


def assert_past_event_llm_invariant(trace: AnalystTrace) -> None:
    """
    Hard regression: past-event analyze without memory or inline facts must not call LLM.
    Raises AssertionError if trace would allow hallucinated analysis.
    """
    if trace.violates_past_event_llm_invariant():
        raise AssertionError(
            "Analyst trace invariant violated: llm_called=True while "
            "is_past_event_request=True, retrieved_memory_items.count=0, "
            "inline_facts_in_message=False"
        )
    trace.apply_past_event_invariant()
    if trace.violates_past_event_llm_invariant():
        raise AssertionError(
            "Analyst trace invariant violated: llm_called=True while "
            "is_past_event_request=True, retrieved_memory_items.count=0, "
            "inline_facts_in_message=False"
        )


def build_detected_intent(
    *,
    state: dict[str, Any],
    past: PastEventResolution | None,
) -> dict[str, Any]:
    planner = state.get("planner_decision") or {}
    intent: dict[str, Any] = {
        "routed_agent": state.get("routed_agent"),
        "interaction_mode": state.get("interaction_mode"),
        "planner_agents": planner.get("agents"),
        "planner_reason": planner.get("reason"),
        "needs_memory": state.get("needs_memory"),
    }
    turn = state_dict(state, "turn_decision")
    if turn:
        intent["semantic_router"] = turn
    if past and past.intent:
        intent["past_event"] = {
            "kind": past.intent.kind,
            "reference_label": past.intent.reference_label,
            "event_focus": past.intent.event_focus,
            "target_date": past.intent.target_date.isoformat()
            if past.intent.target_date
            else None,
        }
    return intent


def citations_to_trace_items(
    citations: list[dict[str, Any]],
) -> list[RetrievedMemoryTraceItem]:
    items: list[RetrievedMemoryTraceItem] = []
    for c in citations:
        snippet = (c.get("snippet") or "")[:120]
        items.append(
            RetrievedMemoryTraceItem(
                memory_id=c.get("turn_id"),
                source=c.get("memory_layer"),
                event_date=None,
                title=snippet,
                match_reason="hybrid_recall",
                similarity_score=float(c.get("score", 0)),
            )
        )
    return items


def attach_router_to_trace(trace: AnalystTrace, turn_decision: dict[str, Any] | None) -> None:
    if not turn_decision:
        return
    trace.turn_intent = turn_decision.get("turn_intent")
    trace.router_reason = turn_decision.get("reason")
    trace.memory_action = turn_decision.get("memory_action")
    trace.event_type = turn_decision.get("event_type")
    trace.event_date = turn_decision.get("event_date")
    trace.recommended_agent = turn_decision.get("recommended_agent")


def trace_from_past_event_resolution(
    *,
    user_input: str,
    state: dict[str, Any],
    past: PastEventResolution | None,
) -> AnalystTrace:
    from app.memory.past_event_guard import user_provided_facts_in_message

    trace = AnalystTrace(user_message=user_input)
    turn = state_dict(state, "turn_decision")
    attach_router_to_trace(trace, turn)
    trace.detected_intent = build_detected_intent(state=state, past=past)

    lookup_intent = turn.get("turn_intent") == "PAST_EVENT_LOOKUP_REQUEST"
    if past is None:
        trace.is_past_event_request = lookup_intent
        trace.inline_facts_in_message = bool(
            turn.get("has_inline_facts")
        ) or user_provided_facts_in_message(user_input)
        return trace

    rt = past.retrieval
    trace.is_past_event_request = lookup_intent or past.is_past_event_request
    trace.memory_query = rt.memory_query
    trace.structured_retrieval_used = rt.structured_retrieval_used
    trace.structured_function_called = rt.structured_function_called
    trace.semantic_fallback_used = rt.semantic_fallback_used
    trace.event_date_parsed = rt.event_date_parsed
    trace.date_normalization_reason = rt.date_normalization_reason
    trace.confidence_score = rt.confidence_score or None
    trace.similarity_score = rt.similarity_score
    trace.inline_facts_in_message = past.inline_facts_in_message
    trace.retrieved_memory_items = list(rt.retrieved_memory_items)
    if not past.llm_allowed:
        trace.blocked_reason = rt.blocked_reason or "past_event_not_found"
        trace.llm_called = False
    trace.inline_facts_in_message = (
        past.inline_facts_in_message or user_provided_facts_in_message(user_input)
    )
    trace.apply_past_event_invariant()
    return trace


def attach_general_memory_recall(
    trace: AnalystTrace,
    *,
    citations: list[dict[str, Any]],
    memory_query: str | None = None,
) -> None:
    if memory_query:
        trace.memory_query = memory_query
    if not trace.is_past_event_request and citations:
        trace.retrieved_memory_items = citations_to_trace_items(citations)
        if citations and trace.similarity_score is None:
            trace.similarity_score = max(float(c.get("score", 0)) for c in citations)


def should_emit_trace(cfg: Settings) -> bool:
    return bool(cfg.development_mode)
