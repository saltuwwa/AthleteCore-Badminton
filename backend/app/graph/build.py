from __future__ import annotations

from contextlib import AsyncExitStack

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from app.config import settings

from .nodes import (
    aggregator_node,
    analyst_node,
    direct_node,
    health_coach_node,
    load_memory_node,
    planner_node,
    route_after_memory,
    route_after_planner,
    scheduler_node,
)
from .state import AthleteGraphState

_exit_stack: AsyncExitStack | None = None
_checkpointer: AsyncSqliteSaver | None = None
_compiled_graph = None


async def init_graph_runtime() -> None:
    """Open SQLite checkpointer (async context manager) and compile the graph."""
    global _exit_stack, _checkpointer, _compiled_graph
    if _compiled_graph is not None:
        return

    _exit_stack = AsyncExitStack()
    _checkpointer = await _exit_stack.enter_async_context(
        AsyncSqliteSaver.from_conn_string(settings.graph_checkpoint_path)
    )
    await _checkpointer.setup()
    _compiled_graph = build_graph().compile(checkpointer=_checkpointer)


async def shutdown_graph_runtime() -> None:
    global _exit_stack, _checkpointer, _compiled_graph
    if _exit_stack is not None:
        await _exit_stack.aclose()
    _exit_stack = None
    _checkpointer = None
    _compiled_graph = None


async def get_checkpointer() -> AsyncSqliteSaver:
    if _checkpointer is None:
        await init_graph_runtime()
    assert _checkpointer is not None
    return _checkpointer


def build_graph():
    builder = StateGraph(AthleteGraphState)

    builder.add_node("load_memory", load_memory_node)
    builder.add_node("planner", planner_node)
    builder.add_node("analyst", analyst_node)
    builder.add_node("health_coach", health_coach_node)
    builder.add_node("scheduler", scheduler_node)
    builder.add_node("direct", direct_node)
    builder.add_node("aggregator", aggregator_node)

    builder.add_edge(START, "planner")
    builder.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "load_memory": "load_memory",
            "analyst": "analyst",
            "health_coach": "health_coach",
            "scheduler": "scheduler",
            "direct": "direct",
        },
    )
    builder.add_conditional_edges(
        "load_memory",
        route_after_memory,
        {
            "analyst": "analyst",
            "health_coach": "health_coach",
            "scheduler": "scheduler",
            "direct": "direct",
        },
    )
    builder.add_edge("analyst", "aggregator")
    builder.add_edge("health_coach", "aggregator")
    builder.add_edge("scheduler", "aggregator")
    builder.add_edge("direct", "aggregator")
    builder.add_edge("aggregator", END)

    return builder


async def get_compiled_graph():
    if _compiled_graph is None:
        await init_graph_runtime()
    assert _compiled_graph is not None
    return _compiled_graph
