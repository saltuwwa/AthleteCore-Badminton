from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.memory.service import MemoryContextService

from .llm import (
    acompletion,
    extract_analysis_json,
    heuristic_route,
    parse_planner_json,
    resolve_analyst_model,
)
from .prompts import (
    AGGREGATOR_SYSTEM,
    ANALYST_SYSTEM,
    DIRECT_SYSTEM,
    HEALTH_COACH_SYSTEM,
    PLANNER_SYSTEM,
    SCHEDULER_SYSTEM,
)
from .context_tools import build_analyst_context, build_scheduler_context
from .memory_gate import resolve_needs_memory
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

    recalled = await _memory_service.recall(
        db,
        query=state.get("user_input", ""),
        session_id=state.get("session_id", "default"),
        user_id=state.get("user_id"),
        max_tokens=1024,
    )
    return {
        "memory_context": recalled.context,
        "memory_citations": [c.model_dump() for c in recalled.citations],
    }


async def planner_node(state: AthleteGraphState, config: RunnableConfig) -> dict[str, Any]:
    user_input = state.get("user_input", "")
    if not settings.openai_api_key and not settings.anthropic_api_key:
        decision = heuristic_route(user_input)
    else:
        try:
            raw = await acompletion(
                model=settings.planner_model,
                messages=[
                    {"role": "system", "content": PLANNER_SYSTEM},
                    {"role": "user", "content": user_input},
                ],
                temperature=0.1,
            )
            decision = parse_planner_json(raw) or heuristic_route(user_input)
        except Exception:
            decision = heuristic_route(user_input)

    agents = decision.get("agents") or ["analyst"]
    if isinstance(agents, str):
        agents = [agents]
    routed: AgentName = "analyst"
    for name in ("analyst", "health_coach", "scheduler", "direct"):
        if name in agents:
            routed = name  # type: ignore[assignment]
            break

    needs_memory = resolve_needs_memory(user_input, routed, decision)

    return {
        "planner_decision": decision,
        "routed_agent": routed,
        "needs_memory": needs_memory,
        "memory_context": "",
        "memory_citations": [],
        "requires_human_confirmation": bool(decision.get("needs_confirmation")),
    }


def route_after_planner(state: AthleteGraphState) -> str:
    """Load LTM first only when planner decided memory is needed."""
    if state.get("needs_memory"):
        return "load_memory"
    return state.get("routed_agent") or "analyst"


def route_after_memory(state: AthleteGraphState) -> str:
    return state.get("routed_agent") or "analyst"


async def analyst_node(state: AthleteGraphState, config: RunnableConfig) -> dict[str, Any]:
    user_input = state.get("user_input", "")
    model = resolve_analyst_model(settings)
    enriched = await build_analyst_context(
        user_input, state.get("memory_context") or ""
    )

    content = await acompletion(
        model=model,
        messages=[
            {"role": "system", "content": ANALYST_SYSTEM},
            {
                "role": "user",
                "content": _user_prompt(user_input, enriched),
            },
        ],
        temperature=0.2,
    )
    analysis = extract_analysis_json(content)
    return {
        "agent_outputs": [
            {
                "agent": "analyst",
                "content": content,
                "analysis": analysis,
            }
        ],
        "agents_used": ["analyst"],
    }


async def health_coach_node(state: AthleteGraphState, config: RunnableConfig) -> dict[str, Any]:
    content = await acompletion(
        model=resolve_analyst_model(settings),
        messages=[
            {"role": "system", "content": HEALTH_COACH_SYSTEM},
            {
                "role": "user",
                "content": _user_prompt(
                    state.get("user_input", ""),
                    state.get("memory_context") or "",
                ),
            },
        ],
        temperature=0.4,
    )
    return {
        "agent_outputs": [{"agent": "health_coach", "content": content}],
        "agents_used": ["health_coach"],
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
    )
    return {
        "agent_outputs": [{"agent": "direct", "content": content}],
        "agents_used": ["direct"],
    }


async def aggregator_node(state: AthleteGraphState, config: RunnableConfig) -> dict[str, Any]:
    outputs = state.get("agent_outputs") or []
    if not outputs:
        return {"final_response": "Не удалось получить ответ агента."}

    if len(outputs) == 1 and not settings.openai_api_key:
        return {"final_response": outputs[0].get("content", "")}

    if len(outputs) == 1:
        return {"final_response": outputs[0].get("content", "")}

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
        final = outputs[0].get("content", "")
    return {"final_response": final}
