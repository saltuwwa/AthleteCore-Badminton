"""LLM semantic turn classification — primary routing; heuristics only on LLM failure."""

from __future__ import annotations

import json
import re
from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.config import Settings, settings
from app.graph.llm import acompletion, parse_planner_json
from app.memory.date_normalizer import (
    apply_calendar_to_semantic_fields,
    reference_local_date,
    resolve_memory_timezone,
)
from app.memory.past_event_guard import has_episodic_substance, user_provided_facts_in_message


def message_has_inline_facts(user_input: str) -> bool:
    """Whether this turn carries new episodic content (router safety, not phrase rules)."""
    text = (user_input or "").strip()
    if not text:
        return False
    if user_provided_facts_in_message(text):
        return True
    t = text.lower()
    if re.search(r"\d+\s*км", t) and (":" in text or text.count(",") >= 1):
        return True
    if re.search(r"\d+\s*[:\-]\s*\d+", t):
        return True
    injury_or_load = any(
        w in t
        for w in (
            "подверн",
            "голеностоп",
            "травм",
            "болит",
            "многоваланк",
            "интервал",
            "бег ",
            "выиграл",
            "проиграл",
            "21:15",
        )
    )
    if injury_or_load and len(t) > 35:
        return True
    return has_episodic_substance({"value": text, "facts": {}})

SEMANTIC_ROUTER_SYSTEM = """You are AthleteCore's semantic turn classifier for a professional badminton athlete assistant.
Classify the MEANING of the user's message. Return STRICT JSON only (no markdown).

Schema:
{
  "turn_intent": "PAST_EVENT_LOOKUP_REQUEST | NEW_EVENT_LOG | CURRENT_SESSION_ANALYSIS | GENERAL_CHAT | ADVICE_REQUEST | HEALTH_CHECK | CALENDAR_ACTION",
  "event_type": "training | match | health | recovery | none",
  "event_date": "YYYY-MM-DD or null",
  "date_confidence": 0.0-1.0,
  "has_inline_facts": true or false,
  "inline_facts_summary": "short summary or empty string",
  "health_signal": true or false,
  "memory_action": "read | write | read_and_write | none",
  "recommended_agent": "analyst | health_coach | planner | direct",
  "reason": "short explanation in Russian"
}

Intent definitions (semantic, not keyword matching):

PAST_EVENT_LOOKUP_REQUEST — user asks to find/analyze a PAST stored record WITHOUT providing new facts now.
Examples: "Разбери мою тренировку 8 февраля", "Сравни с прошлым матчем", "Что было на прошлой тренировке?", "Почему я тогда проиграла?"
has_inline_facts=false when they only ask to retrieve/debrief, not describe what happened.

NEW_EVENT_LOG — user reports NEW facts in this message (training/match/health episode). Memory should be written; do NOT treat as lookup-only.
Examples: "8 февраля была тренировка: бег 5 км, многоваланка, подвернула голеностоп"
"Вчера играла с Машей, выиграла 21:15, но устала"
has_inline_facts=true when concrete sport facts are in the message.

CURRENT_SESSION_ANALYSIS — analyze what they describe now in session without requiring a stored past record lookup first.

GENERAL_CHAT — greetings, small talk, who are you, capabilities. memory_action=none.

ADVICE_REQUEST — general coaching advice (tournament prep, recovery tips) without only asking to pull a past log.

HEALTH_CHECK — fatigue, injury, sleep, nutrition, recovery focus.

CALENDAR_ACTION — schedule changes, weekly plan, propose training blocks. recommended_agent=planner.

Rules:
- If message contains rich episodic facts (scores, drills, injury, opponent) → prefer NEW_EVENT_LOG with has_inline_facts=true and memory_action write or read_and_write.
- If message only asks to "разобрать/найти/сравнить" a date/event without describing it → PAST_EVENT_LOOKUP_REQUEST, has_inline_facts=false, memory_action=read.
- "как дела?" → GENERAL_CHAT.
- Injury/pain in a new log → health_signal=true; recommended_agent may be health_coach if health dominates.
- Resolve relative dates (вчера, позавчера) to ISO using reference_date in the user block.
- date_confidence: high when explicit calendar date, lower for vague "тогда".

Today's reference_date is provided in the user message."""


class TurnIntent(StrEnum):
    PAST_EVENT_LOOKUP_REQUEST = "PAST_EVENT_LOOKUP_REQUEST"
    NEW_EVENT_LOG = "NEW_EVENT_LOG"
    CURRENT_SESSION_ANALYSIS = "CURRENT_SESSION_ANALYSIS"
    GENERAL_CHAT = "GENERAL_CHAT"
    ADVICE_REQUEST = "ADVICE_REQUEST"
    HEALTH_CHECK = "HEALTH_CHECK"
    CALENDAR_ACTION = "CALENDAR_ACTION"
    FOLLOWUP_CONFIRMATION = "FOLLOWUP_CONFIRMATION"
    FOLLOWUP_REJECTION = "FOLLOWUP_REJECTION"
    FOLLOWUP_CLARIFICATION = "FOLLOWUP_CLARIFICATION"


class EventType(StrEnum):
    TRAINING = "training"
    MATCH = "match"
    HEALTH = "health"
    RECOVERY = "recovery"
    NONE = "none"


class MemoryAction(StrEnum):
    READ = "read"
    WRITE = "write"
    READ_AND_WRITE = "read_and_write"
    NONE = "none"


class RecommendedAgent(StrEnum):
    ANALYST = "analyst"
    HEALTH_COACH = "health_coach"
    PLANNER = "planner"
    DIRECT = "direct"


class SemanticTurnDecision(BaseModel):
    turn_intent: TurnIntent
    event_type: EventType = EventType.NONE
    event_date: str | None = None
    date_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    has_inline_facts: bool = False
    inline_facts_summary: str = ""
    health_signal: bool = False
    memory_action: MemoryAction = MemoryAction.NONE
    recommended_agent: RecommendedAgent = RecommendedAgent.ANALYST
    reason: str = ""
    needs_date_clarification: bool = False
    date_clarification_message: str | None = None
    date_normalization: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_date", mode="before")
    @classmethod
    def _empty_date_to_none(cls, v: Any) -> str | None:
        if v is None or v == "" or str(v).lower() in ("null", "none"):
            return None
        return str(v)

    def to_state_dict(self, *, route_source: str = "semantic_router_llm") -> dict[str, Any]:
        return {
            "turn_intent": self.turn_intent.value,
            "event_type": self.event_type.value,
            "event_date": self.event_date,
            "date_confidence": self.date_confidence,
            "has_inline_facts": self.has_inline_facts,
            "inline_facts_summary": self.inline_facts_summary,
            "health_signal": self.health_signal,
            "memory_action": self.memory_action.value,
            "recommended_agent": self.recommended_agent.value,
            "reason": self.reason,
            "needs_date_clarification": self.needs_date_clarification,
            "date_clarification_message": self.date_clarification_message,
            "date_normalization": self.date_normalization,
            "route_source": route_source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SemanticTurnDecision:
        intent = data.get("turn_intent", TurnIntent.CURRENT_SESSION_ANALYSIS.value)
        if intent not in {e.value for e in TurnIntent}:
            intent = TurnIntent.CURRENT_SESSION_ANALYSIS.value
        et = data.get("event_type", "none")
        if et not in {e.value for e in EventType}:
            et = EventType.NONE.value
        agent = data.get("recommended_agent", "analyst")
        if agent not in {e.value for e in RecommendedAgent}:
            agent = RecommendedAgent.ANALYST.value
        ma = data.get("memory_action", "none")
        if ma not in {e.value for e in MemoryAction}:
            ma = MemoryAction.NONE.value
        return cls(
            turn_intent=TurnIntent(intent),
            event_type=EventType(et),
            event_date=data.get("event_date"),
            date_confidence=float(data.get("date_confidence", 0) or 0),
            has_inline_facts=bool(data.get("has_inline_facts")),
            inline_facts_summary=str(data.get("inline_facts_summary") or ""),
            health_signal=bool(data.get("health_signal")),
            memory_action=MemoryAction(ma),
            recommended_agent=RecommendedAgent(agent),
            reason=str(data.get("reason") or ""),
        )


def _parse_router_json(raw: str) -> dict[str, Any]:
    data = parse_planner_json(raw)
    if data.get("turn_intent"):
        return data
    return {}


def fallback_semantic_route(
    user_input: str, *, reference: date | None = None
) -> SemanticTurnDecision:
    """Used only when LLM routing fails — lightweight meaning hints, not primary path."""
    ref = reference or date.today()
    t = (user_input or "").strip().lower()
    if not t:
        return SemanticTurnDecision(
            turn_intent=TurnIntent.GENERAL_CHAT,
            memory_action=MemoryAction.NONE,
            recommended_agent=RecommendedAgent.DIRECT,
            reason="fallback: empty",
        )

    if any(
        p in t
        for p in (
            "как дела",
            "привет",
            "здравств",
            "кто ты",
            "как тебя зовут",
            "что ты умеешь",
            "спасибо",
        )
    ):
        return SemanticTurnDecision(
            turn_intent=TurnIntent.GENERAL_CHAT,
            memory_action=MemoryAction.NONE,
            recommended_agent=RecommendedAgent.DIRECT,
            reason="fallback: general chat markers",
        )

    if message_has_inline_facts(user_input):
        event_type = EventType.TRAINING
        if any(w in t for w in ("матч", "играла", "соперник", "счёт", "счет", ":")):
            event_type = EventType.MATCH
        health = any(w in t for w in ("травм", "болит", "подверн", "голеностоп", "устал"))
        return SemanticTurnDecision(
            turn_intent=TurnIntent.NEW_EVENT_LOG,
            event_type=event_type,
            has_inline_facts=True,
            inline_facts_summary=user_input[:200],
            health_signal=health,
            memory_action=MemoryAction.WRITE,
            recommended_agent=RecommendedAgent.HEALTH_COACH
            if health
            else RecommendedAgent.ANALYST,
            reason="fallback: inline episodic facts detected",
        )

    from app.memory.past_event_intent import detect_past_event_signals

    if detect_past_event_signals(user_input):
        return SemanticTurnDecision(
            turn_intent=TurnIntent.PAST_EVENT_LOOKUP_REQUEST,
            has_inline_facts=False,
            memory_action=MemoryAction.READ,
            recommended_agent=RecommendedAgent.ANALYST,
            reason="fallback: past-event lookup signals",
        )

    if any(w in t for w in ("расписан", "календар", "неделю", "план трен")):
        return SemanticTurnDecision(
            turn_intent=TurnIntent.CALENDAR_ACTION,
            memory_action=MemoryAction.READ,
            recommended_agent=RecommendedAgent.PLANNER,
            reason="fallback: calendar",
        )

    if any(w in t for w in ("совет", "что мне сделать", "как восстанов", "перед турнир")):
        return SemanticTurnDecision(
            turn_intent=TurnIntent.ADVICE_REQUEST,
            memory_action=MemoryAction.READ,
            recommended_agent=RecommendedAgent.ANALYST,
            reason="fallback: advice",
        )

    return SemanticTurnDecision(
        turn_intent=TurnIntent.CURRENT_SESSION_ANALYSIS,
        memory_action=MemoryAction.READ,
        recommended_agent=RecommendedAgent.ANALYST,
        reason="fallback: default session analysis",
    )


def attach_calendar_dates(
    decision: SemanticTurnDecision,
    user_input: str,
    *,
    reference: date,
    timezone: str,
) -> SemanticTurnDecision:
    """Backend calendar arithmetic overrides LLM date strings when text has a parseable date."""
    cal = apply_calendar_to_semantic_fields(
        user_input,
        reference_datetime=reference,
        timezone=timezone,
        llm_event_date=decision.event_date,
        llm_date_confidence=decision.date_confidence,
    )
    norm = cal.to_dict()
    if cal.needs_clarification:
        return decision.model_copy(
            update={
                "event_date": None,
                "date_confidence": 0.0,
                "needs_date_clarification": True,
                "date_clarification_message": cal.clarification_message,
                "date_normalization": norm,
            }
        )
    if cal.resolved and cal.event_date:
        return decision.model_copy(
            update={
                "event_date": cal.event_date.isoformat(),
                "date_confidence": max(decision.date_confidence, cal.confidence),
                "needs_date_clarification": False,
                "date_clarification_message": None,
                "date_normalization": norm,
            }
        )
    return decision.model_copy(update={"date_normalization": norm})


def _finalize_route(
    decision: SemanticTurnDecision,
    user_input: str,
    *,
    ref: date,
    tz: str,
    route_source: str,
) -> SemanticTurnDecision:
    from app.graph.latency_trace import current_latency_trace, stage_span

    trace = current_latency_trace()
    if trace:
        trace.set_meta("route_source", route_source)
    with stage_span("date_normalizer"):
        out = attach_calendar_dates(decision, user_input, reference=ref, timezone=tz)
    out = out.model_copy(
        update={
            "date_normalization": {
                **(out.date_normalization or {}),
                "route_source": route_source,
            }
        }
    )
    return out


async def route_user_turn(
    user_input: str,
    *,
    reference: date | None = None,
    timezone: str | None = None,
    profile_timezone: str | None = None,
    app_settings: Settings | None = None,
    thread_id: str | None = None,
) -> SemanticTurnDecision:
    """Primary path: fast path → cache → LLM semantic classification."""
    from app.cache.router_cache import (
        cache_key as router_cache_key,
        get_cached_router,
        message_blocks_router_cache,
        set_cached_router,
    )
    from app.graph.fast_path_general_chat import try_fast_path_general_chat
    from app.graph.latency_trace import current_latency_trace, stage_span

    cfg = app_settings or settings
    tz = resolve_memory_timezone(
        profile_timezone=profile_timezone,
        app_timezone=timezone or cfg.memory_timezone,
    )
    ref = reference or reference_local_date(timezone=tz)
    trace = current_latency_trace()
    if trace:
        trace.mark("semantic_router_start")

    fast = try_fast_path_general_chat(user_input)
    if fast is not None:
        if trace:
            trace.mark("semantic_router_end")
            trace.set_meta("route_source", "fast_path_general_chat")
        with stage_span("fast_path_general_chat"):
            return _finalize_route(
                fast, user_input, ref=ref, tz=tz, route_source="fast_path_general_chat"
            )

    if not cfg.openai_api_key and not cfg.anthropic_api_key:
        fb = fallback_semantic_route(user_input, reference=ref)
        return _finalize_route(
            fb, user_input, ref=ref, tz=tz, route_source="semantic_router_fallback"
        )

    if not message_blocks_router_cache(user_input):
        rkey = router_cache_key(
            user_input, reference=ref, model=cfg.planner_model, thread_id=thread_id
        )
        cached = get_cached_router(rkey)
        if cached:
            if trace:
                trace.mark("semantic_router_end")
            decision = SemanticTurnDecision.from_dict(cached)
            return _finalize_route(
                decision,
                user_input,
                ref=ref,
                tz=tz,
                route_source="semantic_router_cache",
            )

    user_block = (
        f"reference_date: {ref.isoformat()}\n\nUSER MESSAGE:\n{user_input.strip()}"
    )
    try:
        raw = await acompletion(
            model=cfg.planner_model,
            messages=[
                {"role": "system", "content": SEMANTIC_ROUTER_SYSTEM},
                {"role": "user", "content": user_block},
            ],
            temperature=0.1,
            app_settings=cfg,
            latency_name="semantic_router",
        )
        data = _parse_router_json(raw)
        if data:
            decision = SemanticTurnDecision.from_dict(data)
            # Code may tighten has_inline_facts for safety, never loosen lookup→log
            substantive_inline = (
                user_provided_facts_in_message(user_input)
                or (
                    message_has_inline_facts(user_input)
                    and (":" in user_input or re.search(r"\d+\s*км", user_input.lower()))
                )
            )
            if (
                decision.turn_intent == TurnIntent.PAST_EVENT_LOOKUP_REQUEST
                and substantive_inline
                and not decision.has_inline_facts
            ):
                decision = decision.model_copy(
                    update={
                        "turn_intent": TurnIntent.NEW_EVENT_LOG,
                        "has_inline_facts": True,
                        "memory_action": MemoryAction.WRITE,
                        "reason": decision.reason + " [code: inline facts override]",
                    }
                )
            if not message_blocks_router_cache(user_input):
                rkey = router_cache_key(
                    user_input, reference=ref, model=cfg.planner_model, thread_id=thread_id
                )
                cache_payload = decision.to_state_dict()
                cache_payload.pop("route_source", None)
                set_cached_router(rkey, cache_payload)
            if trace:
                trace.mark("semantic_router_end")
            return _finalize_route(
                decision,
                user_input,
                ref=ref,
                tz=tz,
                route_source="semantic_router_llm",
            )
    except Exception:
        pass

    if trace:
        trace.mark("semantic_router_end")
    fb = fallback_semantic_route(user_input, reference=ref)
    return _finalize_route(
        fb, user_input, ref=ref, tz=tz, route_source="semantic_router_fallback"
    )


def agent_name_for_graph(decision: SemanticTurnDecision) -> str:
    """Map router agent to LangGraph specialist node."""
    mapping = {
        RecommendedAgent.ANALYST: "analyst",
        RecommendedAgent.HEALTH_COACH: "health_coach",
        RecommendedAgent.PLANNER: "scheduler",
        RecommendedAgent.DIRECT: "direct",
    }
    return mapping.get(decision.recommended_agent, "analyst")


def needs_memory_for_decision(decision: SemanticTurnDecision) -> bool:
    return decision.memory_action in (MemoryAction.READ, MemoryAction.READ_AND_WRITE)


def should_persist_memory(decision: SemanticTurnDecision) -> bool:
    return decision.memory_action in (MemoryAction.WRITE, MemoryAction.READ_AND_WRITE)
