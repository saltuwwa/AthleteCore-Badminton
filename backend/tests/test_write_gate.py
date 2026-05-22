from app.memory.mapping import memory_layer_for, normalize_candidate
from app.memory.models import MemoryLayer
from app.memory.write_gate import MemoryWriteGate


def test_procedural_layer():
    assert memory_layer_for("fact", "agent.response_style") == MemoryLayer.procedural


def test_write_gate_hitl():
    gate = MemoryWriteGate()
    c = normalize_candidate(
        {
            "type": "event",
            "key": "schedule.confirmation",
            "value": "User rejected AI-added evening block",
            "is_user_confirmed": True,
        }
    )
    filtered = gate.filter_candidates([c])
    assert len(filtered) == 1


def test_write_gate_small_talk_blocked_by_extraction_not_gate():
    gate = MemoryWriteGate()
    d = gate.should_write(is_small_talk=True)
    assert not d.allow
