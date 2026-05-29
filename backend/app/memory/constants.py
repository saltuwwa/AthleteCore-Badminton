"""Structured memory field constants (schema v1+)."""

from __future__ import annotations

MEMORY_SCHEMA_VERSION = 1
DEFAULT_SPORT = "badminton"

# sources — who produced the memory content
SOURCE_USER = "user"
SOURCE_ASSISTANT = "assistant"
SOURCE_VIDEO_PIPELINE = "video_pipeline"
SOURCE_DOCUMENT_PIPELINE = "document_pipeline"
SOURCE_CONFIRMED_ANALYSIS = "confirmed_analysis"

ALLOWED_SOURCES = frozenset(
    {
        SOURCE_USER,
        SOURCE_ASSISTANT,
        SOURCE_VIDEO_PIPELINE,
        SOURCE_DOCUMENT_PIPELINE,
        SOURCE_CONFIRMED_ANALYSIS,
    }
)

WRITABLE_SOURCES = frozenset(
    {
        SOURCE_USER,
        SOURCE_VIDEO_PIPELINE,
        SOURCE_DOCUMENT_PIPELINE,
        SOURCE_CONFIRMED_ANALYSIS,
    }
)

# session_type — sport event category
SESSION_MATCH = "match"
SESSION_TRAINING = "training"
SESSION_RECOVERY = "recovery"
SESSION_HEALTH = "health"
SESSION_TOURNAMENT = "tournament"
SESSION_NOTE = "note"

ALLOWED_SESSION_TYPES = frozenset(
    {
        SESSION_MATCH,
        SESSION_TRAINING,
        SESSION_RECOVERY,
        SESSION_HEALTH,
        SESSION_TOURNAMENT,
        SESSION_NOTE,
    }
)

EPISODIC_EVENT_TYPES = frozenset(
    {
        "match_log",
        "training_log",
        "video_analysis",
        "competition_document_analysis",
    }
)
