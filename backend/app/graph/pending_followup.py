"""Thread-scoped pending yes/no follow-ups from assistant offers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.graph.interaction import is_analysis_consent, is_analysis_refusal
from app.graph.semantic_router import (
    MemoryAction,
    RecommendedAgent,
    SemanticTurnDecision,
    TurnIntent,
    message_has_inline_facts,
)
from app.memory.past_event_intent import detect_past_event_signals

_CONFIRM_RE = re.compile(
    r"^(да|ага|угу|давай|окей|ок|okay|yes|yep|конечно|разумеется|go ahead|поехали|можно)[!.?\s]*$",
    re.IGNORECASE,
)
_REJECT_RE = re.compile(
    r"^(нет|не надо|не нужно|не сейчас|потом|позже|no|not now|later)[!.?\s]*$",
    re.IGNORECASE,
)
_YES_NO_OFFER_RE = re.compile(r"\(да\s*/\s*нет\)|да\s+или\s+нет", re.IGNORECASE)


@dataclass
class FollowupResolveResult:
    decision: SemanticTurnDecision | None = None
    clear_pending: bool = False
    action_taken: str | None = None
    pending_followup_detected: bool = False
    followup_type: str | None = None
    source_agent: str | None = None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def is_short_reply(text: str, *, max_len: int = 40) -> bool:
    t = _normalize(text)
    return bool(t) and len(t) <= max_len


def is_followup_confirmation(text: str) -> bool:
    t = _normalize(text).lower()
    if not t:
        return False
    if _CONFIRM_RE.match(t):
        return True
    # Only treat very short consent-like replies as confirmation (not «разбери тренировку»).
    return len(t) <= 20 and is_analysis_consent(text) and not is_topic_change(text)


def is_followup_rejection(text: str) -> bool:
    t = _normalize(text).lower()
    if not t:
        return False
    if _REJECT_RE.match(t):
        return True
    return len(t) <= 20 and is_analysis_refusal(text)


def is_topic_change(text: str) -> bool:
    """Full new request — do not treat as yes/no to prior offer."""
    t = _normalize(text)
    if len(t) > 55:
        return True
    if detect_past_event_signals(t):
        return True
    if message_has_inline_facts(t):
        return True
    if any(
        w in t.lower()
        for w in (
            "разбери",
            "трениров",
            "матч",
            "расписан",
            "календар",
            "вчера была",
            "как восстанов",
            "проанализ",
        )
    ):
        return True
    return False


def is_ambiguous_short_confirmation(text: str) -> bool:
    """Bare «да» / «ок» with no pending offer in thread."""
    t = _normalize(text).lower()
    if not is_short_reply(text):
        return False
    return bool(_CONFIRM_RE.match(t) or _REJECT_RE.match(t))


def _followup_type_for_offer(offer: str, source_agent: str) -> str:
    if source_agent == "health_coach":
        return "health_recovery_breakdown"
    if offer == "performance_deeper":
        return "performance_deeper_review"
    return "analyst_error_breakdown"


def build_pending_followup(
    offer: str,
    *,
    source_agent: str,
    assistant_message: str,
    prior_user_message: str = "",
) -> dict[str, Any]:
    followup_type = _followup_type_for_offer(offer, source_agent)
    question = assistant_message.strip()
    if len(question) > 400:
        question = question[-400:]
    action_on_yes: dict[str, Any] = {
        "agent": source_agent,
        "interaction_mode": "full_analysis",
    }
    if followup_type == "health_recovery_breakdown":
        action_on_yes["instruction"] = (
            "structured_recovery_breakdown: ankle sprain recovery in 5 numbered sections"
        )
    elif followup_type == "analyst_error_breakdown":
        action_on_yes["instruction"] = "structured_error_breakdown_by_points"
    else:
        action_on_yes["instruction"] = "structured_performance_review"

    return {
        "pending_followup": True,
        "followup_type": followup_type,
        "source_agent": source_agent,
        "question": question,
        "expected_replies": [
            "да",
            "нет",
            "ага",
            "давай",
            "окей",
            "yes",
            "no",
            "конечно",
            "не надо",
            "позже",
        ],
        "action_on_yes": action_on_yes,
        "action_on_no": {
            "message": (
                "Хорошо. Если захочешь вернуться к разбору — просто напиши, "
                "и продолжим с того места."
            ),
        },
        "prior_user_message": prior_user_message[:500],
        "prior_assistant_message": assistant_message[:2000],
        "offer_type": offer,
    }


def pending_from_state(
    pending_followup: dict[str, Any] | None,
    *,
    prior_offer: str | None = None,
) -> dict[str, Any] | None:
    if pending_followup and pending_followup.get("pending_followup"):
        return pending_followup
    if prior_offer:
        source = "health_coach" if prior_offer == "analysis_debrief" else "analyst"
        return {
            "pending_followup": True,
            "followup_type": _followup_type_for_offer(prior_offer, source),
            "source_agent": source,
            "question": "",
            "expected_replies": ["да", "нет"],
            "action_on_yes": {
                "agent": "analyst",
                "interaction_mode": "full_analysis",
                "instruction": "structured_error_breakdown_by_points",
            },
            "action_on_no": {
                "message": "Хорошо, без разбора. Если понадобится — напиши.",
            },
            "offer_type": prior_offer,
        }
    return None


def assistant_offered_yes_no(assistant_message: str) -> bool:
    return bool(_YES_NO_OFFER_RE.search(assistant_message or ""))


def _agent_enum(name: str) -> RecommendedAgent:
    mapping = {
        "analyst": RecommendedAgent.ANALYST,
        "health_coach": RecommendedAgent.HEALTH_COACH,
        "scheduler": RecommendedAgent.PLANNER,
        "direct": RecommendedAgent.DIRECT,
    }
    return mapping.get(name, RecommendedAgent.ANALYST)


def try_resolve_followup_turn(
    user_input: str,
    pending: dict[str, Any] | None,
    *,
    prior_offer: str | None = None,
    thread_id: str | None = None,
) -> FollowupResolveResult | None:
    """
    Resolve short yes/no using thread pending follow-up.
    Returns None to continue normal routing (e.g. topic change).
    """
    active = pending_from_state(pending, prior_offer=prior_offer)
    if not active and thread_id:
        active = get_thread_pending_followup(thread_id)
    if not active:
        if is_ambiguous_short_confirmation(user_input):
            return FollowupResolveResult(
                decision=SemanticTurnDecision(
                    turn_intent=TurnIntent.FOLLOWUP_CLARIFICATION,
                    memory_action=MemoryAction.NONE,
                    recommended_agent=RecommendedAgent.DIRECT,
                    reason="ambiguous short confirmation without pending offer",
                ),
                action_taken="ask_clarification",
            )
        return None

    meta = {
        "pending_followup_detected": True,
        "followup_type": active.get("followup_type"),
        "source_agent": active.get("source_agent"),
    }

    if is_topic_change(user_input):
        return FollowupResolveResult(
            clear_pending=True,
            pending_followup_detected=True,
            followup_type=active.get("followup_type"),
            source_agent=active.get("source_agent"),
            action_taken="topic_change_clear_pending",
        )

    if is_followup_confirmation(user_input):
        action = active.get("action_on_yes") or {}
        agent_name = str(action.get("agent") or active.get("source_agent") or "analyst")
        return FollowupResolveResult(
            decision=SemanticTurnDecision(
                turn_intent=TurnIntent.FOLLOWUP_CONFIRMATION,
                memory_action=MemoryAction.READ,
                recommended_agent=_agent_enum(agent_name),
                health_signal=active.get("followup_type") == "health_recovery_breakdown",
                reason="pending_followup: user confirmed prior offer",
            ),
            clear_pending=True,
            action_taken=str(action.get("instruction") or "continue_followup"),
            pending_followup_detected=True,
            followup_type=active.get("followup_type"),
            source_agent=active.get("source_agent"),
        )

    if is_followup_rejection(user_input):
        agent_name = str(active.get("source_agent") or "direct")
        return FollowupResolveResult(
            decision=SemanticTurnDecision(
                turn_intent=TurnIntent.FOLLOWUP_REJECTION,
                memory_action=MemoryAction.NONE,
                recommended_agent=_agent_enum(agent_name),
                reason="pending_followup: user declined prior offer",
            ),
            clear_pending=True,
            action_taken="polite_close",
            pending_followup_detected=True,
            followup_type=active.get("followup_type"),
            source_agent=active.get("source_agent"),
        )

    return None


def enrich_turn_decision(
    turn_dict: dict[str, Any],
    *,
    resolve: FollowupResolveResult | None = None,
    pending: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = dict(turn_dict)
    if resolve:
        out["pending_followup_detected"] = resolve.pending_followup_detected
        out["followup_type"] = resolve.followup_type
        out["source_agent"] = resolve.source_agent
        out["action_taken"] = resolve.action_taken
    elif pending and pending.get("pending_followup"):
        out["pending_followup_detected"] = True
        out["followup_type"] = pending.get("followup_type")
        out["source_agent"] = pending.get("source_agent")
    else:
        out.setdefault("pending_followup_detected", False)
    return out


# Thread mirror (checkpoint + in-process) for yes/no continuity per conversation.
_thread_pending_followup: dict[str, dict[str, Any]] = {}


def set_thread_pending_followup(thread_id: str, payload: dict[str, Any] | None) -> None:
    if payload and payload.get("pending_followup"):
        _thread_pending_followup[thread_id] = payload
    else:
        _thread_pending_followup.pop(thread_id, None)


def get_thread_pending_followup(thread_id: str) -> dict[str, Any] | None:
    return _thread_pending_followup.get(thread_id)
