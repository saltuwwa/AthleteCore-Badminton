"""LangGraph Overwrite unwrap helpers."""

from __future__ import annotations

from langgraph.types import Overwrite

from app.graph.state_utils import state_dict, unwrap_overwrite


def test_overwrite_dict_is_truthy_but_unwrapped():
    wrapped = Overwrite({})
    assert bool(wrapped)
    assert state_dict({"turn_decision": wrapped}, "turn_decision") == {}


def test_state_dict_returns_plain_dict():
    state = {"turn_decision": {"turn_intent": "NEW_EVENT_LOG"}}
    assert state_dict(state, "turn_decision").get("turn_intent") == "NEW_EVENT_LOG"


def test_unwrap_overwrite_value():
    assert unwrap_overwrite(Overwrite([])) == []
