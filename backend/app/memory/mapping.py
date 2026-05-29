"""Map structured extraction rows → AthleteCore memory layers (semantic/episodic/procedural)."""

from __future__ import annotations

from typing import Any

from .models import ExtractedMemoryType, MemoryLayer, RiskLevel

PROCEDURAL_PREFIXES = ("agent.", "hitl.", "interaction.")

SEMANTIC_KEY_PREFIXES = (
    "training.",
    "health.",
    "goal.",
    "schedule.preference.",
    "recovery.",
    "constraint.",
    "profile.",
)

EPISODIC_KEY_PREFIXES = (
    "match.",
    "performance.",
    "training.session.",
    "schedule.confirmation.",
    "video.analysis.",
    "competition.document.",
)


def memory_layer_for(mem_type: str, key: str) -> MemoryLayer:
    k = key.lower().strip()
    if any(k.startswith(p) for p in PROCEDURAL_PREFIXES):
        return MemoryLayer.procedural
    if mem_type == ExtractedMemoryType.event.value:
        return MemoryLayer.episodic
    if any(k.startswith(p) for p in EPISODIC_KEY_PREFIXES):
        return MemoryLayer.episodic
    return MemoryLayer.semantic


def infer_event_type(key: str, mem_type: str) -> str | None:
    k = key.lower()
    if mem_type != ExtractedMemoryType.event.value and not k.startswith("match."):
        if not k.startswith("training.session.") and not k.startswith("schedule.confirmation."):
            return None
    if k.startswith("match.") or "match" in k:
        return "match_log"
    if k.startswith("schedule.confirmation") or k.startswith("hitl."):
        return "schedule_confirmation"
    if k.startswith("video.analysis."):
        return "video_analysis"
    if k.startswith("competition.document."):
        return "competition_document_analysis"
    if k.startswith("training.") or k.startswith("performance."):
        return "training_log"
    return "training_log" if mem_type == ExtractedMemoryType.event.value else None


def parse_risk_level(raw: str | None) -> RiskLevel | None:
    if not raw:
        return None
    try:
        return RiskLevel(str(raw).lower())
    except ValueError:
        return None


def normalize_candidate(raw: dict[str, Any]) -> dict[str, Any]:
    """Enrich extractor output with AthleteCore fields."""
    mem_type = str(raw.get("type", "fact")).lower()
    key = str(raw["key"]).strip()
    layer = memory_layer_for(mem_type, key)
    event_type = raw.get("event_type") or infer_event_type(key, mem_type)
    risk = parse_risk_level(raw.get("risk_level"))
    importance = float(raw.get("importance", 0.5))
    if risk == RiskLevel.high:
        importance = max(importance, 0.9)
    elif risk == RiskLevel.med:
        importance = max(importance, 0.7)

    facts = raw.get("facts")
    if not isinstance(facts, dict):
        facts = {}

    return {
        "type": mem_type,
        "key": key,
        "value": str(raw["value"]).strip(),
        "confidence": float(raw.get("confidence", 0.8)),
        "implicit_from": raw.get("implicit_from"),
        "supersedes_same_key": bool(raw.get("supersedes_same_key", False)),
        "memory_layer": layer.value,
        "event_type": event_type,
        "risk_level": risk.value if risk else None,
        "importance": importance,
        "is_repeated_pattern": bool(raw.get("is_repeated_pattern", False)),
        "is_user_confirmed": bool(raw.get("is_user_confirmed", False)),
        "payload": raw.get("payload") if isinstance(raw.get("payload"), dict) else {},
        "session_type": raw.get("session_type"),
        "event_date": raw.get("event_date"),
        "event_date_end": raw.get("event_date_end"),
        "event_date_phrase": raw.get("event_date_phrase"),
        "facts": facts,
        "source": raw.get("source"),
        "sport": raw.get("sport"),
        "schema_version": raw.get("schema_version"),
    }
