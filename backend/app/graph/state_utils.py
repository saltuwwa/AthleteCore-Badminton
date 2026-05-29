"""Normalize LangGraph state values (unwrap Overwrite wrappers)."""

from __future__ import annotations

from typing import Any

try:
    from langgraph.types import Overwrite
except ImportError:  # pragma: no cover
    Overwrite = None  # type: ignore[misc, assignment]


def unwrap_overwrite(value: Any) -> Any:
    """Return inner value if LangGraph Overwrite command leaked into readable state."""
    if Overwrite is not None and isinstance(value, Overwrite):
        return value.value
    return value


def state_dict(state: dict[str, Any], key: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = unwrap_overwrite(state.get(key))
    if isinstance(raw, dict):
        return raw
    return default if default is not None else {}


def state_list(
    state: dict[str, Any], key: str, default: list[Any] | None = None
) -> list[Any]:
    raw = unwrap_overwrite(state.get(key))
    if isinstance(raw, list):
        return raw
    return default if default is not None else []


def state_str(state: dict[str, Any], key: str, default: str = "") -> str:
    raw = unwrap_overwrite(state.get(key))
    return raw if isinstance(raw, str) else default
