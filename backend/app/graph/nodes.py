from __future__ import annotations

from datetime import date
from typing import Any

from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.memory.service import MemoryContextService

from .llm import (
    acompletion,
    extract_analysis_json,
    resolve_analyst_model,
)
from .interaction import (
    offer_followup_for_mode,
    resolve_coaching_tone,
    resolve_interaction_mode,
    support_instructions_block,
)
from app.graph.latency_trace import current_latency_trace, stage_span
from app.graph.pending_followup import (
    build_pending_followup,
    enrich_turn_decision,
    set_thread_pending_followup,
    try_resolve_followup_turn,
)
from app.graph.semantic_router import _finalize_route
from app.graph.analyst_trace import (
    assert_past_event_llm_invariant,
    attach_general_memory_recall,
    should_emit_trace,
    trace_from_past_event_resolution,
)
from app.graph.semantic_router import (
    TurnIntent,
    agent_name_for_graph,
    needs_memory_for_decision,
    route_user_turn,
    should_persist_memory,
)
from app.graph.state_utils import state_dict, state_list
from app.graph.turn_safety import evaluate_turn_safety
from app.memory.past_event_guard import (
    PastEventResolution,
    PastEventRetrievalTrace,
    build_not_found_reply,
    format_inline_message_grounding,
    resolve_past_event,
)
from .prompts import (
    AGGREGATOR_SYSTEM,
    ANALYST_CELEBRATE_SYSTEM,
    ANALYST_COMPARISON_SYSTEM,
    ANALYST_DIRECT_SYSTEM,
    ANALYST_SUPPORT_SYSTEM,
    ANALYST_SYSTEM,
    ANALYST_TOUGH_SYSTEM,
    DIRECT_SYSTEM,
    HEALTH_COACH_SYSTEM,
    SCHEDULER_SYSTEM,
)
from .context_tools import build_analyst_context, build_scheduler_context
from .state import AgentName, AthleteGraphState

_memory_service = MemoryContextService()


def _cfg(config: RunnableConfig) -> dict[str, Any]:
    return config.get("configurable") or {}


def _user_prompt(user_input: str, memory_context: str) -> str:
    ctx = (memory_context or "").strip()
    if not ctx:
        return f"USER MESSAGE:\n{user_input}"
    return f"MEMORY CONTEXT:\n{ctx}\n\nUSER MESSAGE:\n{user_input}"


async def load_memory_node(
    state: AthleteGraphState, config: RunnableConfig
) -> dict[str, Any]:
    if not state.get("needs_memory"):
        return {"memory_context": "", "memory_citations": []}

    db: AsyncSession | None = _cfg(config).get("db_session")
    if db is None:
        return {"memory_context": "", "memory_citations": []}

    with stage_span("memory_recall"):
        recalled = await _memory_service.recall(
            db,
            query=state.get("user_input", ""),
            session_id=state.get("session_id", "main"),
            user_id=state.get("user_id"),
            max_tokens=1024,
        )
    return {
        "memory_context": recalled.context,
        "memory_citations": [c.model_dump() for c in recalled.citations],
    }


async def planner_node(state: AthleteGraphState, config: RunnableConfig) -> dict[str, Any]:
    trace = current_latency_trace()
    if trace:
        trace.mark("planner_start")
    user_input = state.get("user_input", "")
    tz = settings.memory_timezone
    prior_offer = state.get("offer_followup")
    prior_pending = state.get("pending_followup")
    followup_resolve = try_resolve_followup_turn(
        user_input,
        prior_pending,
        prior_offer=prior_offer,
        thread_id=state.get("thread_id"),
    )

    if trace := current_latency_trace():
        if followup_resolve and followup_resolve.pending_followup_detected:
            trace.set_meta("pending_followup_detected", True)
            if followup_resolve.followup_type:
                trace.set_meta("followup_type", followup_resolve.followup_type)
            if followup_resolve.source_agent:
                trace.set_meta("source_agent", followup_resolve.source_agent)
            if followup_resolve.action_taken:
                trace.set_meta("action_taken", followup_resolve.action_taken)

    clear_pending = bool(
        followup_resolve
        and followup_resolve.clear_pending
        and followup_resolve.decision is None
    )
    if followup_resolve and followup_resolve.decision is not None:
        from app.memory.date_normalizer import reference_local_date

        ref = reference_local_date(timezone=tz)
        semantic = _finalize_route(
            followup_resolve.decision,
            user_input,
            ref=ref,
            tz=tz,
            route_source="pending_followup",
        )
    else:
        semantic = await route_user_turn(
            user_input,
            timezone=tz,
            app_settings=settings,
            thread_id=state.get("thread_id"),
        )

    route_src = (semantic.date_normalization or {}).get(
        "route_source", "semantic_router_llm"
    )
    if trace := current_latency_trace():
        trace.set_meta("route_source", route_src)
        trace.set_meta("turn_intent", semantic.turn_intent.value)
        trace.set_meta("memory_action", semantic.memory_action.value)
        trace.set_meta("event_type", semantic.event_type.value)
        ed = semantic.date_normalization or {}
        if ed.get("event_date"):
            trace.set_meta("event_date", ed.get("event_date"))
        if semantic.health_signal:
            trace.set_meta("health_signal", True)
    routed: AgentName = agent_name_for_graph(semantic)  # type: ignore[assignment]

    interaction_mode = resolve_interaction_mode(
        user_input,
        prior_offer=None if clear_pending else prior_offer,
        planner_mode=None,
    )
    if semantic.turn_intent == TurnIntent.FOLLOWUP_CONFIRMATION:
        pending_action = (prior_pending or {}).get("action_on_yes") or {}
        interaction_mode = pending_action.get("interaction_mode", "full_analysis")  # type: ignore[assignment]
    elif semantic.turn_intent == TurnIntent.FOLLOWUP_REJECTION:
        interaction_mode = "neutral"
    elif semantic.turn_intent == TurnIntent.FOLLOWUP_CLARIFICATION:
        interaction_mode = "neutral"
    elif semantic.turn_intent == TurnIntent.GENERAL_CHAT:
        interaction_mode = "neutral"
    elif semantic.turn_intent in (TurnIntent.NEW_EVENT_LOG, TurnIntent.PAST_EVENT_LOOKUP_REQUEST):
        interaction_mode = "full_analysis"
    elif semantic.health_signal:
        interaction_mode = "support_first"

    coaching_tone = "gentle"
    needs_memory = needs_memory_for_decision(semantic)
    if semantic.turn_intent == TurnIntent.FOLLOWUP_CONFIRMATION:
        needs_memory = True
    if interaction_mode in ("support_first", "celebrate_first", "full_analysis"):
        needs_memory = needs_memory or semantic.turn_intent not in (
            TurnIntent.GENERAL_CHAT,
            TurnIntent.FOLLOWUP_CLARIFICATION,
        )

    planner_decision = {
        "agents": [routed],
        "reason": semantic.reason,
        "turn_intent": semantic.turn_intent.value,
        "needs_memory": needs_memory,
        "needs_confirmation": semantic.turn_intent == TurnIntent.CALENDAR_ACTION,
        "interaction_mode": interaction_mode,
    }

    # Preserve pending through this turn so specialist can read it; agent clears after consume.
    preserve_pending_for_agent = semantic.turn_intent in (
        TurnIntent.FOLLOWUP_CONFIRMATION,
        TurnIntent.FOLLOWUP_REJECTION,
    )
    next_pending: dict[str, Any] | None
    if clear_pending:
        next_pending = None
        set_thread_pending_followup(state.get("thread_id", ""), None)
    elif preserve_pending_for_agent:
        next_pending = prior_pending
    else:
        next_pending = prior_pending if prior_pending else None

    turn_decision = enrich_turn_decision(
        semantic.to_state_dict(route_source=route_src),
        resolve=followup_resolve,
        pending=prior_pending,
    )

    return {
        "planner_decision": planner_decision,
        "turn_decision": turn_decision,
        "routed_agent": routed,
        "needs_memory": needs_memory,
        "persist_memory": should_persist_memory(semantic),
        "interaction_mode": interaction_mode,
        "coaching_tone": coaching_tone,
        "memory_context": "",
        "memory_citations": [],
        "requires_human_confirmation": semantic.turn_intent == TurnIntent.CALENDAR_ACTION,
        "pending_followup": next_pending,
        "offer_followup": prior_offer if preserve_pending_for_agent else (None if clear_pending else prior_offer),
    }


def route_after_planner(state: AthleteGraphState) -> str:
    """Load LTM first only when planner decided memory is needed."""
    if state.get("needs_memory"):
        return "load_memory"
    return state.get("routed_agent") or "analyst"


def route_after_memory(state: AthleteGraphState) -> str:
    return state.get("routed_agent") or "analyst"


def _analyst_system_prompt(mode: str, coaching_tone: str = "gentle") -> str:
    if mode == "support_first":
        return ANALYST_SUPPORT_SYSTEM
    if mode == "celebrate_first":
        return ANALYST_CELEBRATE_SYSTEM
    if mode in ("full_analysis", "neutral"):
        if coaching_tone == "tough":
            return ANALYST_TOUGH_SYSTEM
        if coaching_tone == "direct":
            return ANALYST_DIRECT_SYSTEM
        return ANALYST_SYSTEM
    return ANALYST_SYSTEM


def _resolution_for_new_event_log(
    user_input: str, turn_decision: dict[str, Any]
) -> PastEventResolution:
    ref_label = turn_decision.get("event_date") or "событие из текущего сообщения"
    summary = (turn_decision.get("inline_facts_summary") or "").strip()
    if summary:
        ref_label = summary[:120]
    return PastEventResolution(
        is_past_event_query=False,
        found=True,
        reference_label=ref_label,
        confidence=1.0,
        grounding_context=format_inline_message_grounding(
            user_input, reference_label=ref_label
        ),
        inline_facts_in_message=True,
        llm_allowed=True,
        retrieval=PastEventRetrievalTrace(memory_query=user_input[:240]),
    )


async def _past_event_resolution_for_analyst(
    state: AthleteGraphState, config: RunnableConfig
) -> PastEventResolution | None:
    user_input = state.get("user_input", "")
    turn = state_dict(state, "turn_decision")
    intent = turn.get("turn_intent")

    if intent == TurnIntent.NEW_EVENT_LOG.value:
        return _resolution_for_new_event_log(user_input, turn)

    if intent != TurnIntent.PAST_EVENT_LOOKUP_REQUEST.value:
        return None

    db: AsyncSession | None = _cfg(config).get("db_session")
    if db is None:
        return PastEventResolution(
            is_past_event_query=True,
            found=False,
            reference_label=turn.get("event_date") or "прошлое событие",
            llm_allowed=False,
            missing_message=(
                "Я не могу проверить память о прошлом событии (нет подключения к базе). "
                "Опиши тренировку или матч в этом сообщении."
            ),
            retrieval=PastEventRetrievalTrace(
                blocked_reason="db_session_unavailable",
            ),
        )

    from app.memory.embeddings import embed_query, openai_client

    user_id = state.get("user_id")
    session_id = state.get("session_id", "main")
    q_emb: list[float] | None = None
    if settings.openai_api_key:
        try:
            client = openai_client(settings)
            q_emb = await embed_query(
                client,
                settings.embedding_model,
                user_input,
                dimensions=settings.embedding_dimensions,
            )
        except Exception:
            q_emb = None

    return await resolve_past_event(
        db,
        user_input=user_input,
        user_id=user_id,
        session_id=session_id,
        reference=date.today(),
        query_embedding=q_emb,
    )


def _memory_context_for_analyst(
    memory_context: str,
    past_event: PastEventResolution | None,
    turn_decision: dict[str, Any] | None,
) -> str:
    """Hybrid recall must not ground a specific past event/date — only structured/inline facts."""
    turn = turn_decision or {}
    if turn.get("turn_intent") == TurnIntent.NEW_EVENT_LOG.value:
        return memory_context
    if past_event is None:
        return memory_context
    if not past_event.is_past_event_request:
        return memory_context
    if past_event.inline_facts_in_message:
        return memory_context
    return ""


def _blocked_analyst_return(
    *,
    reply: str,
    trace: Any,
    past_event: PastEventResolution | None,
    emit_trace: bool,
    safety_applied: str | None,
) -> dict[str, Any]:
    trace.llm_called = False
    trace.safety_invariant_applied = safety_applied
    trace_payload = trace.to_dict() if emit_trace else None
    return {
        "agent_outputs": [
            {
                "agent": "analyst",
                "content": reply,
                "analysis": None,
                "comparison_status": "not_found",
                "comparison_label": past_event.reference_label if past_event else None,
                "chat_actions": past_event.chat_actions if past_event else [],
                "llm_called": False,
                "past_event_status": "not_found",
                "analyst_trace": trace_payload,
            }
        ],
        "agents_used": ["analyst"],
        "offer_followup": None,
        "llm_called": False,
        "analyst_trace": trace_payload,
    }


async def analyst_node(state: AthleteGraphState, config: RunnableConfig) -> dict[str, Any]:
    user_input = state.get("user_input", "")
    mode = state.get("interaction_mode") or "neutral"
    memory_context = state.get("memory_context") or ""
    turn_decision = state_dict(state, "turn_decision")
    if turn_decision.get("needs_date_clarification"):
        msg = (
            turn_decision.get("date_clarification_message")
            or "Уточни дату события."
        )
        trace = trace_from_past_event_resolution(
            user_input=user_input,
            state=dict(state),
            past=None,
        )
        trace.safety_invariant_applied = "invalid_calendar_date"
        trace_payload = trace.to_dict() if should_emit_trace(settings) else None
        return _blocked_analyst_return(
            reply=msg,
            trace=trace,
            past_event=None,
            emit_trace=should_emit_trace(settings),
            safety_applied="invalid_calendar_date",
        )

    past_event = await _past_event_resolution_for_analyst(state, config)
    trace = trace_from_past_event_resolution(
        user_input=user_input,
        state=dict(state),
        past=past_event,
    )
    attach_general_memory_recall(
        trace,
        citations=state.get("memory_citations") or [],
        memory_query=user_input if not trace.memory_query else None,
    )
    emit_trace = should_emit_trace(settings)
    with stage_span("turn_safety"):
        safety = evaluate_turn_safety(turn_decision, past_event)
    trace.safety_invariant_applied = safety.safety_invariant_applied

    if safety.block_llm:
        if past_event is None:
            trace.is_past_event_request = True
            trace.blocked_reason = trace.blocked_reason or "past_event_guard_unavailable"
            reply = (
                "Я не могу проверить память о прошлой тренировке. "
                "Опиши событие в этом сообщении или добавь его в историю."
            )
            return _blocked_analyst_return(
                reply=reply,
                trace=trace,
                past_event=None,
                emit_trace=emit_trace,
                safety_applied=safety.safety_invariant_applied,
            )
        trace.apply_past_event_invariant()
        reply = build_not_found_reply(past_event)
        return _blocked_analyst_return(
            reply=reply,
            trace=trace,
            past_event=past_event,
            emit_trace=emit_trace,
            safety_applied=safety.safety_invariant_applied,
        )

    effective_memory_context = _memory_context_for_analyst(
        memory_context, past_event, turn_decision
    )
    coaching_tone = resolve_coaching_tone(
        user_input, effective_memory_context, mode  # type: ignore[arg-type]
    )
    model = resolve_analyst_model(settings)
    enriched = await build_analyst_context(
        user_input,
        effective_memory_context,
        turn_decision=turn_decision,
        past_event_found=bool(past_event and past_event.found),
    )
    if past_event and past_event.found and past_event.grounding_context:
        enriched = f"{enriched}\n\n{past_event.grounding_context}"
    support_block = support_instructions_block(effective_memory_context, mode)  # type: ignore[arg-type]
    user_blob = _user_prompt(user_input, enriched)
    if support_block:
        user_blob = f"{support_block}\n\n{user_blob}"

    if past_event and past_event.found:
        system_prompt = ANALYST_COMPARISON_SYSTEM
    else:
        system_prompt = _analyst_system_prompt(mode, coaching_tone)

    if mode in ("support_first", "celebrate_first"):
        temp = 0.35
    elif coaching_tone in ("direct", "tough"):
        temp = 0.15
    else:
        temp = 0.2

    prompt_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_blob},
    ]
    trace.final_prompt_sent_to_llm = {
        "model": model,
        "temperature": temp,
        "messages": prompt_messages,
    }
    assert_past_event_llm_invariant(trace)
    if (
        turn_decision.get("turn_intent") == TurnIntent.PAST_EVENT_LOOKUP_REQUEST.value
        and trace.retrieved_memory_items_count == 0
        and not trace.inline_facts_in_message
        and not (past_event and past_event.llm_allowed)
    ):
        trace.llm_called = False
        trace.blocked_reason = trace.blocked_reason or "past_event_no_retrieved_memory"
        trace.safety_invariant_applied = "invariant_1_past_no_retrieved_memory"
        reply = (
            build_not_found_reply(past_event)
            if past_event
            else "Я не нашёл данных о прошлом событии. Опиши его в сообщении или добавь в историю."
        )
        return _blocked_analyst_return(
            reply=reply,
            trace=trace,
            past_event=past_event,
            emit_trace=emit_trace,
            safety_applied=trace.safety_invariant_applied,
        )

    content = await acompletion(
        model=model,
        messages=prompt_messages,
        temperature=temp,
        latency_name="analyst",
    )
    trace.llm_called = True
    trace.raw_llm_response = content
    analysis = None
    if mode in ("full_analysis", "neutral"):
        with stage_span("response_parsing"):
            analysis = extract_analysis_json(content)
        trace.parsed_json_response = analysis
        if analysis and past_event and past_event.found:
            analysis.setdefault(
                "comparison_label",
                f"Сравнение с: {past_event.reference_label}",
            )

    if emit_trace:
        trace_payload = trace.to_dict()

    offer = offer_followup_for_mode(mode)  # type: ignore[arg-type]
    pending = None
    if offer:
        pending = build_pending_followup(
            offer,
            source_agent="analyst",
            assistant_message=content,
            prior_user_message=user_input,
        )
        set_thread_pending_followup(state.get("thread_id", ""), pending)
    out: dict[str, Any] = {
        "agent": "analyst",
        "content": content,
        "analysis": analysis,
        "llm_called": True,
        "analyst_trace": trace_payload,
    }
    if past_event and past_event.found:
        out["comparison_status"] = "found"
        out["comparison_label"] = past_event.reference_label
    elif past_event and past_event.is_past_event_query:
        out["comparison_status"] = "found" if past_event.found else "not_found"
    return {
        "agent_outputs": [
            {
                **out,
                "past_event_status": "grounded" if past_event and past_event.found else None,
            }
        ],
        "agents_used": ["analyst"],
        "offer_followup": offer,
        "pending_followup": pending,
        "llm_called": trace.llm_called,
        "analyst_trace": trace_payload,
    }


async def health_coach_node(state: AthleteGraphState, config: RunnableConfig) -> dict[str, Any]:
    turn = state_dict(state, "turn_decision")
    prior_pending = state.get("pending_followup") or {}

    if turn.get("turn_intent") == TurnIntent.FOLLOWUP_REJECTION.value:
        msg = (prior_pending.get("action_on_no") or {}).get("message") or (
            "Хорошо, без разбора. Если понадобится — напиши."
        )
        set_thread_pending_followup(state.get("thread_id", ""), None)
        return {
            "agent_outputs": [{"agent": "health_coach", "content": msg}],
            "agents_used": ["health_coach"],
            "offer_followup": None,
            "pending_followup": None,
        }

    if turn.get("turn_intent") == TurnIntent.FOLLOWUP_CONFIRMATION.value:
        from .prompts import HEALTH_FOLLOWUP_BREAKDOWN_SYSTEM

        prior_user = prior_pending.get("prior_user_message") or ""
        prior_assistant = prior_pending.get("prior_assistant_message") or ""
        user_blob = (
            f"PRIOR USER MESSAGE:\n{prior_user}\n\n"
            f"PRIOR ASSISTANT MESSAGE (with yes/no offer):\n{prior_assistant}\n\n"
            f"USER CONFIRMATION NOW:\n{state.get('user_input', '')}\n\n"
            f"MEMORY CONTEXT:\n{(state.get('memory_context') or '').strip()}"
        )
        content = await acompletion(
            model=resolve_analyst_model(settings),
            messages=[
                {"role": "system", "content": HEALTH_FOLLOWUP_BREAKDOWN_SYSTEM},
                {"role": "user", "content": user_blob},
            ],
            temperature=0.25,
            latency_name="health_coach",
        )
        set_thread_pending_followup(state.get("thread_id", ""), None)
        return {
            "agent_outputs": [{"agent": "health_coach", "content": content}],
            "agents_used": ["health_coach"],
            "offer_followup": None,
            "pending_followup": None,
        }

    mode = state.get("interaction_mode") or "neutral"
    memory_context = state.get("memory_context") or ""
    support_block = support_instructions_block(memory_context, mode)  # type: ignore[arg-type]
    user_blob = _user_prompt(state.get("user_input", ""), memory_context)
    if support_block:
        user_blob = f"{support_block}\n\n{user_blob}"
    content = await acompletion(
        model=resolve_analyst_model(settings),
        messages=[
            {"role": "system", "content": HEALTH_COACH_SYSTEM},
            {"role": "user", "content": user_blob},
        ],
        temperature=0.4,
        latency_name="health_coach",
    )
    offer = offer_followup_for_mode(mode) if mode in ("support_first", "celebrate_first") else None  # type: ignore[arg-type]
    pending = None
    if offer:
        pending = build_pending_followup(
            offer,
            source_agent="health_coach",
            assistant_message=content,
            prior_user_message=state.get("user_input", ""),
        )
        set_thread_pending_followup(state.get("thread_id", ""), pending)
    return {
        "agent_outputs": [{"agent": "health_coach", "content": content}],
        "agents_used": ["health_coach"],
        "offer_followup": offer,
        "pending_followup": pending,
    }


async def scheduler_node(state: AthleteGraphState, config: RunnableConfig) -> dict[str, Any]:
    user_input = state.get("user_input", "")
    user_id = state.get("user_id", "aigerim")
    enriched = await build_scheduler_context(
        user_input, state.get("memory_context") or "", user_id
    )

    content = await acompletion(
        model=settings.planner_model,
        messages=[
            {"role": "system", "content": SCHEDULER_SYSTEM},
            {
                "role": "user",
                "content": _user_prompt(user_input, enriched),
            },
        ],
        temperature=0.3,
        latency_name="scheduler",
    )

    pending_note = await _maybe_propose_schedule_from_reply(
        content, user_id=user_id, user_input=user_input
    )
    if pending_note:
        content = f"{content}\n\n{pending_note}"

    return {
        "agent_outputs": [{"agent": "scheduler", "content": content}],
        "agents_used": ["scheduler"],
        "requires_human_confirmation": True,
    }


async def _maybe_propose_schedule_from_reply(
    reply: str, *, user_id: str, user_input: str
) -> str | None:
    """If the model outputs a PROPOSE line, register pending calendar block."""
    import re

    from app.mcp_tools.schedule import propose_training_block

    m = re.search(
        r"PROPOSE:\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})-(\d{2}:\d{2})\s+\|\s+(.+?)\s+\|\s+(\w+)",
        reply,
        re.IGNORECASE,
    )
    if not m:
        return None
    date_s, start, end, title, etype = m.groups()
    try:
        result = await propose_training_block(
            user_id=user_id,
            title=title.strip(),
            event_date=date_s,
            start_time=start,
            end_time=end,
            event_type=etype.upper(),
            intensity=3,
            reason=user_input[:500],
        )
        return f"📅 {result['message']} (id: {result['id']})"
    except Exception as exc:
        return f"📅 Не удалось создать черновик в календаре: {exc}"


async def direct_node(state: AthleteGraphState, config: RunnableConfig) -> dict[str, Any]:
    turn = state_dict(state, "turn_decision")
    if turn.get("turn_intent") == TurnIntent.FOLLOWUP_CLARIFICATION.value:
        return {
            "agent_outputs": [
                {
                    "agent": "direct",
                    "content": (
                        "К чему именно ты отвечаешь «да»? "
                        "Уточни, пожалуйста — к разбору тренировки, восстановлению или другому вопросу."
                    ),
                }
            ],
            "agents_used": ["direct"],
            "offer_followup": None,
            "pending_followup": None,
        }

    content = await acompletion(
        model=settings.direct_model,
        messages=[
            {"role": "system", "content": DIRECT_SYSTEM},
            {
                "role": "user",
                "content": _user_prompt(
                    state.get("user_input", ""),
                    state.get("memory_context") or "",
                ),
            },
        ],
        temperature=0.3,
        latency_name="direct",
    )
    return {
        "agent_outputs": [{"agent": "direct", "content": content}],
        "agents_used": ["direct"],
    }


async def aggregator_node(state: AthleteGraphState, config: RunnableConfig) -> dict[str, Any]:
    outputs = state_list(state, "agent_outputs")
    if not outputs:
        return {"final_response": "Не удалось получить ответ агента."}

    latest = outputs[-1]

    if len(outputs) == 1 and not settings.openai_api_key:
        out = {"final_response": latest.get("content", "")}
        if "offer_followup" in state:
            out["offer_followup"] = state.get("offer_followup")
        if "pending_followup" in state:
            out["pending_followup"] = state.get("pending_followup")
        return out

    if len(outputs) == 1:
        out = {"final_response": latest.get("content", "")}
        if "offer_followup" in state:
            out["offer_followup"] = state.get("offer_followup")
        if "pending_followup" in state:
            out["pending_followup"] = state.get("pending_followup")
        return out

    merged_blob = "\n\n".join(
        f"[{o.get('agent', 'agent')}]\n{o.get('content', '')}" for o in outputs
    )
    try:
        final = await acompletion(
            model=settings.aggregator_model,
            messages=[
                {"role": "system", "content": AGGREGATOR_SYSTEM},
                {"role": "user", "content": merged_blob},
            ],
            temperature=0.2,
        )
    except Exception:
        final = latest.get("content", "")
    out: dict[str, Any] = {"final_response": final}
    if "offer_followup" in state:
        out["offer_followup"] = state.get("offer_followup")
    if "pending_followup" in state:
        out["pending_followup"] = state.get("pending_followup")
    return out
