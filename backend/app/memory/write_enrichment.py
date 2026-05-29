"""Enrich extraction candidates with structured fields before DB insert."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .constants import (
    DEFAULT_SPORT,
    EPISODIC_EVENT_TYPES,
    MEMORY_SCHEMA_VERSION,
    SESSION_MATCH,
    SESSION_NOTE,
    SESSION_TRAINING,
    SOURCE_USER,
)
from .date_normalizer import DEFAULT_MEMORY_TIMEZONE, normalize_memory_event_dates
from .mapping import infer_event_type, memory_layer_for


def _reference_date(turn_timestamp: datetime | date | None) -> date:
    if turn_timestamp is None:
        return date.today()
    if isinstance(turn_timestamp, datetime):
        return turn_timestamp.date()
    return turn_timestamp


def infer_session_type(
    key: str,
    event_type: str | None,
    raw_session_type: str | None = None,
) -> str | None:
    if raw_session_type:
        st = raw_session_type.lower().strip()
        if st in {"match", "training", "recovery", "health", "tournament", "note"}:
            return st
    k = key.lower()
    et = (event_type or "").lower()
    if et == "match_log" or k.startswith("match."):
        return SESSION_MATCH
    if et == "training_log" or k.startswith("training.session."):
        return SESSION_TRAINING
    if k.startswith("health."):
        return "health"
    if k.startswith("recovery."):
        return "recovery"
    if k.startswith("competition.document."):
        return "tournament"
    if et in EPISODIC_EVENT_TYPES:
        return SESSION_NOTE
    return None


def is_episodic_candidate(candidate: dict[str, Any]) -> bool:
    layer = candidate.get("memory_layer", "")
    et = candidate.get("event_type")
    if layer == "episodic":
        return True
    return et in EPISODIC_EVENT_TYPES


def enrich_candidate(
    candidate: dict[str, Any],
    *,
    raw_user_text: str | None,
    turn_timestamp: datetime | date | None,
    default_source: str = SOURCE_USER,
    timezone: str = DEFAULT_MEMORY_TIMEZONE,
) -> dict[str, Any]:
    """Apply schema v1 structured fields on top of normalized extractor output."""
    ref = _reference_date(turn_timestamp)
    key = candidate.get("key", "")
    event_type = candidate.get("event_type") or infer_event_type(
        key, str(candidate.get("type", "fact"))
    )
    candidate["event_type"] = event_type
    candidate["memory_layer"] = candidate.get("memory_layer") or memory_layer_for(
        str(candidate.get("type", "fact")), key
    ).value
    candidate["sport"] = candidate.get("sport") or DEFAULT_SPORT
    candidate["schema_version"] = MEMORY_SCHEMA_VERSION
    candidate["source"] = candidate.get("source") or default_source

    episodic = is_episodic_candidate(candidate)
    user_blob = (raw_user_text or "").strip()

    if episodic and user_blob:
        candidate["raw_user_text"] = user_blob
    elif not episodic:
        candidate["raw_user_text"] = None

    candidate["session_type"] = infer_session_type(
        key,
        event_type,
        candidate.get("session_type"),
    )

    facts = candidate.get("facts")
    if not isinstance(facts, dict):
        facts = {}
    candidate["facts"] = facts

    if episodic:
        date_res = normalize_memory_event_dates(
            user_blob or candidate.get("value", ""),
            turn_timestamp=turn_timestamp if isinstance(turn_timestamp, datetime) else None,
            reference_datetime=turn_timestamp,
            timezone=timezone,
            summary_text=str(candidate.get("value", "")),
            event_date_iso=candidate.get("event_date"),
            event_date_end_iso=candidate.get("event_date_end"),
            event_date_phrase=candidate.get("event_date_phrase"),
        )
        candidate["event_date"] = date_res.event_date
        candidate["event_date_end"] = date_res.event_date_end
        if date_res.resolved:
            candidate["facts"] = {
                **candidate.get("facts", {}),
                "event_date_confidence": date_res.confidence,
                "date_resolution_reason": date_res.date_resolution_reason,
            }
    else:
        candidate["event_date"] = parse_optional_date(candidate.get("event_date"))
        candidate["event_date_end"] = parse_optional_date(candidate.get("event_date_end"))

    return candidate


def parse_optional_date(value: Any) -> date | None:
    from .date_normalizer import parse_iso_date

    return parse_iso_date(value)


def enrich_candidates_for_turn(
    candidates: list[dict[str, Any]],
    *,
    raw_user_text: str,
    turn_timestamp: datetime | date | None,
    default_source: str = SOURCE_USER,
    timezone: str = DEFAULT_MEMORY_TIMEZONE,
) -> list[dict[str, Any]]:
    return [
        enrich_candidate(
            c,
            raw_user_text=raw_user_text,
            turn_timestamp=turn_timestamp,
            default_source=default_source,
            timezone=timezone,
        )
        for c in candidates
    ]
