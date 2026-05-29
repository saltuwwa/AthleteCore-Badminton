"""Code-enforced safety invariants on top of LLM semantic classification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.graph.semantic_router import TurnIntent
from app.graph.state_utils import unwrap_overwrite
from app.memory.past_event_guard import PastEventResolution


@dataclass(slots=True)
class TurnSafetyResult:
    block_llm: bool
    safety_invariant_applied: str | None
    force_comparison_status: str | None = None
    allow_analysis: bool = True


def evaluate_turn_safety(
    turn_decision: dict[str, Any] | None,
    past_event: PastEventResolution | None,
) -> TurnSafetyResult:
    """
    Invariant 1: PAST_EVENT_LOOKUP + no inline facts + 0 records → block analysis LLM.
    Invariant 2: NEW_EVENT_LOG → never block as not_found.
    Invariant 3: GENERAL_CHAT → no past-event not_found semantics.
    """
    turn_decision = unwrap_overwrite(turn_decision)
    if not turn_decision or not isinstance(turn_decision, dict):
        return TurnSafetyResult(block_llm=False, safety_invariant_applied=None)

    intent = turn_decision.get("turn_intent")
    has_inline = bool(turn_decision.get("has_inline_facts"))

    if intent == TurnIntent.GENERAL_CHAT.value:
        return TurnSafetyResult(
            block_llm=False,
            safety_invariant_applied="invariant_3_general_chat",
            force_comparison_status=None,
            allow_analysis=False,
        )

    if intent == TurnIntent.NEW_EVENT_LOG.value:
        return TurnSafetyResult(
            block_llm=False,
            safety_invariant_applied="invariant_2_new_event_log",
            allow_analysis=True,
        )

    if intent == TurnIntent.PAST_EVENT_LOOKUP_REQUEST.value:
        if has_inline:
            return TurnSafetyResult(
                block_llm=False,
                safety_invariant_applied="past_lookup_with_inline_facts",
                allow_analysis=True,
            )
        if past_event is None:
            return TurnSafetyResult(
                block_llm=True,
                safety_invariant_applied="invariant_1_past_guard_unavailable",
                force_comparison_status="not_found",
                allow_analysis=False,
            )
        if not past_event.llm_allowed or (
            past_event.is_past_event_request and not past_event.found
        ):
            return TurnSafetyResult(
                block_llm=True,
                safety_invariant_applied="invariant_1_past_not_found",
                force_comparison_status="not_found",
                allow_analysis=False,
            )
        return TurnSafetyResult(
            block_llm=False,
            safety_invariant_applied="past_lookup_grounded",
            allow_analysis=True,
        )

    if intent in (
        TurnIntent.ADVICE_REQUEST.value,
        TurnIntent.CURRENT_SESSION_ANALYSIS.value,
        TurnIntent.HEALTH_CHECK.value,
    ):
        return TurnSafetyResult(
            block_llm=False,
            safety_invariant_applied="advisory_or_session_no_forced_lookup",
            allow_analysis=True,
        )

    return TurnSafetyResult(block_llm=False, safety_invariant_applied=None)
