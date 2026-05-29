from datetime import date

from app.memory.constants import SOURCE_CONFIRMED_ANALYSIS, SOURCE_USER
from app.memory.mapping import memory_layer_for, normalize_candidate
from app.memory.memory_classification import (
    FACT_PENDING_UNRESOLVED_DATE,
    SportMemoryCategory,
    classify_sport_memory,
    detect_noise_intent,
)
from app.memory.models import MemoryLayer
from app.memory.write_gate import MemoryWriteGate


def test_procedural_layer():
    assert memory_layer_for("fact", "agent.response_style") == MemoryLayer.procedural


def test_classify_match_and_training():
    m = normalize_candidate(
        {"type": "event", "key": "match.latest", "value": "Win vs Lee", "event_type": "match_log"}
    )
    assert classify_sport_memory(m) == SportMemoryCategory.MATCH_LOG
    t = normalize_candidate(
        {
            "type": "event",
            "key": "training.session.latest",
            "value": "Силовая 90 мин RPE 7",
            "event_type": "training_log",
        }
    )
    assert classify_sport_memory(t) == SportMemoryCategory.TRAINING_LOG


def test_detect_noise_intent():
    assert detect_noise_intent("Какая погода завтра?") == "noise-intent"
    assert detect_noise_intent("Перенеси тренировку на 18:00") == "calendar-crud"
    assert detect_noise_intent("Разбери мою тренировку") == "analysis-request-without-facts"


def test_write_gate_confirmed_coach_feedback():
    gate = MemoryWriteGate()
    c = normalize_candidate(
        {
            "type": "fact",
            "key": "performance.error.pattern",
            "value": "Late contact on backhand",
            "source": SOURCE_CONFIRMED_ANALYSIS,
            "is_user_confirmed": True,
        }
    )
    assert len(gate.filter_candidates([c])) == 1


def test_write_gate_blocks_schedule_and_procedural():
    gate = MemoryWriteGate()
    schedule = normalize_candidate(
        {
            "type": "event",
            "key": "schedule.confirmation",
            "value": "User rejected block",
            "is_user_confirmed": True,
            "event_type": "schedule_confirmation",
        }
    )
    agent = normalize_candidate(
        {"type": "fact", "key": "agent.response_style", "value": "direct"}
    )
    assert gate.filter_candidates([schedule]) == []
    assert gate.filter_candidates([agent]) == []


def test_write_gate_blocks_generic_fact():
    gate = MemoryWriteGate()
    c = normalize_candidate({"type": "fact", "key": "profile.nickname", "value": "Ace"})
    c["source"] = SOURCE_USER
    assert gate.filter_candidates([c]) == []


def test_write_gate_blocks_weakness_without_recurrence():
    gate = MemoryWriteGate()
    c = normalize_candidate(
        {
            "type": "fact",
            "key": "performance.error.pattern",
            "value": "Late split-step sometimes",
            "source": SOURCE_USER,
        }
    )
    assert gate.filter_candidates([c]) == []


def test_write_gate_allows_recurring_weakness():
    gate = MemoryWriteGate()
    c = normalize_candidate(
        {
            "type": "fact",
            "key": "performance.error.pattern",
            "value": "Late split-step on backhand",
            "is_repeated_pattern": True,
            "source": SOURCE_USER,
        }
    )
    assert len(gate.filter_candidates([c])) == 1


def test_write_gate_resolved_episodic_with_date():
    gate = MemoryWriteGate()
    c = normalize_candidate(
        {
            "type": "event",
            "key": "training.session.latest",
            "value": "Силовая тренировка 90 минут, RPE 7",
            "event_type": "training_log",
        }
    )
    c["source"] = SOURCE_USER
    c["event_date"] = date(2026, 5, 28)
    c["facts"] = {"event_date_confidence": 0.97}
    assert len(gate.filter_candidates([c])) == 1


def test_write_gate_pending_without_date():
    gate = MemoryWriteGate()
    c = normalize_candidate(
        {
            "type": "event",
            "key": "training.session.latest",
            "value": "Силовая тренировка 90 минут, RPE 7",
            "event_type": "training_log",
        }
    )
    c["source"] = SOURCE_USER
    c["event_date"] = None
    out = gate.filter_candidates([c])
    assert len(out) == 1
    assert out[0]["facts"][FACT_PENDING_UNRESOLVED_DATE] is True
    assert out[0]["event_date"] is None


def test_write_gate_blocks_bare_episodic_without_date():
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


def test_write_gate_blocks_analysis_request_noise():
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
    assert (
        gate.filter_candidates([c], raw_user_text="Разбери мою тренировку") == []
    )


def test_write_gate_small_talk():
    gate = MemoryWriteGate()
    d = gate.should_write(is_small_talk=True)
    assert not d.allow
