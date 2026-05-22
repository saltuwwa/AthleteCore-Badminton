from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

AgentName = Literal["analyst", "health_coach", "scheduler", "direct"]


class AthleteGraphState(TypedDict, total=False):
    """LangGraph state — STM persisted via checkpointer on thread_id."""

    thread_id: str
    user_id: str
    session_id: str
    user_input: str

    memory_context: str
    memory_citations: list[dict[str, Any]]

    planner_decision: dict[str, Any]
    routed_agent: AgentName
    needs_memory: bool

    agent_outputs: Annotated[list[dict[str, Any]], operator.add]

    requires_human_confirmation: bool
    final_response: str
    agents_used: list[str]
