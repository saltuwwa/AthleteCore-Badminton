from datetime import date, datetime, timezone

from app.memory.constants import SOURCE_USER
from app.memory.mapping import normalize_candidate
from app.memory.write_enrichment import enrich_candidate
from app.memory.write_gate import MemoryWriteGate


def test_enrich_yesterday_training():
    raw = normalize_candidate(
        {
            "type": "event",
            "key": "training.session.latest",
            "value": "Силовая тренировка 90 мин, RPE 7",
            "event_type": "training_log",
            "session_type": "training",
        }
    )
    enriched = enrich_candidate(
        raw,
        raw_user_text="Вчера была тренировка, 90 минут, RPE 7",
        turn_timestamp=datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc),
        default_source=SOURCE_USER,
    )
    assert enriched["event_date"] == date(2026, 5, 28)
    assert enriched["raw_user_text"].startswith("Вчера")
    assert enriched["source"] == SOURCE_USER
    assert enriched["session_type"] == "training"


def test_write_gate_blocks_episodic_without_substance():
    gate = MemoryWriteGate()
    c = normalize_candidate(
        {
            "type": "event",
            "key": "training.session.latest",
            "value": "some training",
            "event_type": "training_log",
        }
    )
    c["source"] = SOURCE_USER
    c["event_date"] = None
    assert gate.filter_candidates([c]) == []


def test_write_gate_blocks_assistant_source():
    gate = MemoryWriteGate()
    c = normalize_candidate(
        {
            "type": "fact",
            "key": "performance.error.pattern",
            "value": "Assistant invented fatigue",
        }
    )
    c["source"] = "assistant"
    assert gate.filter_candidates([c]) == []
