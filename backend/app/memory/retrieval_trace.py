"""Shared trace DTOs for memory read path (past-event guard + Analyst dev trace)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class RetrievedMemoryTraceItem:
    memory_id: str | None = None
    source: str | None = None
    event_date: str | None = None
    title: str = ""
    match_reason: str | None = None
    similarity_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def memory_row_to_trace_item(
    memory: Any,
    *,
    match_reason: str | None = None,
    similarity_score: float | None = None,
) -> RetrievedMemoryTraceItem:
    title = (getattr(memory, "value", None) or str(memory))[:120]
    ed = getattr(memory, "event_date", None)
    return RetrievedMemoryTraceItem(
        memory_id=str(getattr(memory, "id", "")) or None,
        source=getattr(memory, "source", None),
        event_date=ed.isoformat() if ed else None,
        title=title,
        match_reason=match_reason,
        similarity_score=similarity_score,
    )


def format_memory_query_for_intent(
    user_input: str,
    *,
    kind: str | None,
    reference_label: str | None,
    target_date_iso: str | None = None,
    opponent: str | None = None,
) -> str:
    if kind:
        parts = [f"past_event:{kind}", reference_label or ""]
        if target_date_iso:
            parts.append(target_date_iso)
        if opponent:
            parts.append(f"opponent:{opponent}")
        return " | ".join(p for p in parts if p)
    return user_input.strip()
