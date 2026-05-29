"""Classify extractor candidates into allowed sport-memory categories."""

from __future__ import annotations

from enum import Enum
from typing import Any

from .constants import (
    SOURCE_CONFIRMED_ANALYSIS,
    SOURCE_DOCUMENT_PIPELINE,
    SOURCE_VIDEO_PIPELINE,
)

# Minimum confidence from date_normalizer to treat episodic date as usable in SQL retrieval.
MIN_EPISODIC_DATE_CONFIDENCE = 0.75

FACT_PENDING_UNRESOLVED_DATE = "pending_unresolved_date"


class SportMemoryCategory(str, Enum):
    MATCH_LOG = "match_log"
    TRAINING_LOG = "training_log"
    HEALTH_LOG = "health_log"
    RECOVERY_LOG = "recovery_log"
    INJURY_NOTE = "injury_note"
    GOAL = "goal"
    RECURRING_WEAKNESS = "recurring_weakness"
    CONFIRMED_COACH_FEEDBACK = "confirmed_coach_feedback"
    TOURNAMENT_RESULT = "tournament_result"
    VIDEO_ANALYSIS = "video_analysis"
    COMPETITION_DOCUMENT_ANALYSIS = "competition_document_analysis"


ALLOWED_SPORT_CATEGORIES = frozenset(SportMemoryCategory)

# Shared with memory_gate — structured off-topic / transactional intents (substring markers).
NOISE_INTENT_MARKERS: tuple[str, ...] = (
    "погод",
    "weather",
    "температур",
    "дожд",
    "прогноз",
    "привет",
    "как дела",
    "спасибо",
    "пока",
    "hello",
    "hi there",
    "good morning",
)

CALENDAR_CRUD_MARKERS: tuple[str, ...] = (
    "перенес",
    "перенест",
    "сдвин",
    "отмен",
    "удали событ",
    "убери событ",
    "измени время",
    "поменяй время",
    "reschedule",
    "move event",
    "cancel event",
    "delete event",
)

UI_COMMAND_MARKERS: tuple[str, ...] = (
    "/help",
    "/reset",
    "очисти чат",
    "clear chat",
    "новый чат",
)

ANALYSIS_ONLY_MARKERS: tuple[str, ...] = (
    "разбери",
    "проанализируй",
    "analyze my",
    "break down my",
    "разбор трениров",
    "разбор матч",
)

PROCEDURAL_KEY_PREFIXES: tuple[str, ...] = (
    "agent.",
    "interaction.",
    "hitl.",
    "training.preference.",
    "schedule.preference.",
)

SPORT_SUBSTANCE_KEYS = frozenset(
    {
        "opponent",
        "score",
        "errors",
        "fatigue",
        "drills",
        "rpe",
        "duration",
        "issues",
        "detected_issues",
    }
)


def _lower(value: Any) -> str:
    return str(value or "").lower().strip()


def event_date_confidence(candidate: dict[str, Any]) -> float:
    facts = candidate.get("facts")
    if isinstance(facts, dict):
        try:
            return float(facts.get("event_date_confidence", 0.0))
        except (TypeError, ValueError):
            pass
    return 0.0


def has_episodic_substance(candidate: dict[str, Any]) -> bool:
    """True when the row carries concrete sport facts, not a bare analysis request."""
    facts = candidate.get("facts")
    if isinstance(facts, dict):
        for key in SPORT_SUBSTANCE_KEYS:
            val = facts.get(key)
            if val is None or val == "" or val == []:
                continue
            return True

    value = _lower(candidate.get("value"))
    if len(value) < 24:
        return False

    sport_tokens = (
        "трениров",
        "матч",
        "rpe",
        "соперник",
        "счёт",
        "счет",
        "ошиб",
        "устал",
        "минут",
        "подач",
        "match",
        "training",
        "opponent",
        "score",
        "fatigue",
    )
    return any(tok in value for tok in sport_tokens)


def detect_noise_intent(raw_user_text: str | None) -> str | None:
    """Return block reason for non-sport transactional / chit-chat input."""
    text = _lower(raw_user_text)
    if not text:
        return None
    if any(m in text for m in NOISE_INTENT_MARKERS):
        return "noise-intent"
    if any(m in text for m in CALENDAR_CRUD_MARKERS):
        return "calendar-crud"
    if any(m in text for m in UI_COMMAND_MARKERS):
        return "ui-command"
    if is_analysis_only_request(text) and len(text) < 120:
        if not any(tok in text for tok in ("rpe", "минут", "счёт", "счет", "соперник", "score")):
            return "analysis-request-without-facts"
    return None


def is_analysis_only_request(text: str) -> bool:
    t = _lower(text)
    return any(m in t for m in ANALYSIS_ONLY_MARKERS)


def classify_sport_memory(candidate: dict[str, Any]) -> SportMemoryCategory | None:
    """Map a normalized candidate to an allowed sport-memory category, if any."""
    source = _lower(candidate.get("source"))
    key = _lower(candidate.get("key"))
    event_type = _lower(candidate.get("event_type"))
    session_type = _lower(candidate.get("session_type"))

    if source == SOURCE_CONFIRMED_ANALYSIS:
        return SportMemoryCategory.CONFIRMED_COACH_FEEDBACK

    if event_type == "video_analysis" or key.startswith("video.analysis."):
        return SportMemoryCategory.VIDEO_ANALYSIS

    if (
        event_type == "competition_document_analysis"
        or key.startswith("competition.document.")
        or source == SOURCE_DOCUMENT_PIPELINE
    ):
        return SportMemoryCategory.COMPETITION_DOCUMENT_ANALYSIS

    if source in {SOURCE_VIDEO_PIPELINE} and event_type == "video_analysis":
        return SportMemoryCategory.VIDEO_ANALYSIS

    if event_type == "match_log" or key.startswith("match.") or session_type == "match":
        return SportMemoryCategory.MATCH_LOG

    if (
        event_type == "training_log"
        or key.startswith("training.session.")
        or session_type == "training"
    ):
        return SportMemoryCategory.TRAINING_LOG

    if key.startswith("health.injury") or session_type == "health" and "injur" in key:
        return SportMemoryCategory.INJURY_NOTE

    if key.startswith("health.") or session_type == "health":
        return SportMemoryCategory.HEALTH_LOG

    if key.startswith("recovery.") or session_type == "recovery":
        return SportMemoryCategory.RECOVERY_LOG

    if key.startswith("goal."):
        return SportMemoryCategory.GOAL

    if key.startswith("performance.error.") or key.startswith("performance.weakness"):
        return SportMemoryCategory.RECURRING_WEAKNESS

    if session_type == "tournament" or "tournament" in key:
        return SportMemoryCategory.TOURNAMENT_RESULT

    if event_type in {c.value for c in SportMemoryCategory}:
        return SportMemoryCategory(event_type)

    return None


def is_procedural_disallowed(candidate: dict[str, Any]) -> bool:
    key = _lower(candidate.get("key"))
    event_type = _lower(candidate.get("event_type"))
    if event_type == "schedule_confirmation":
        return True
    return any(key.startswith(p) for p in PROCEDURAL_KEY_PREFIXES)
