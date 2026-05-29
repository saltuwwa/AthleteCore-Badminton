"""Tests for comparison intent parsing and honest not-found guard."""

from app.graph.match_comparison import (
    build_suggestions_from_memories,
    is_comparison_query,
    parse_comparison_intent,
    resolve_comparison,
)
from app.memory.models import ExtractedMemoryType, Memory, MemoryLayer


def _mem(key: str, value: str, *, event_type: str | None = "match_log") -> Memory:
    return Memory(
        key=key,
        value=value,
        memory_type=ExtractedMemoryType.event,
        memory_layer=MemoryLayer.episodic,
        event_type=event_type,
        confidence=0.9,
        importance=0.8,
        source_session="main",
        source_turn_id=__import__("uuid").uuid4(),
        active=True,
    )


def test_is_comparison_query_ru():
    assert is_comparison_query("Сравни с матчем 15 апр")
    assert not is_comparison_query("Какая погода завтра?")


def test_parse_date_intent():
    intent = parse_comparison_intent("Сравни с матчем 15 апр")
    assert intent is not None
    assert intent.kind == "date"
    assert intent.day == 15
    assert intent.month == 4


def test_resolve_not_found_without_memory():
    intent = parse_comparison_intent("Сравни с матчем 15 апр")
    assert intent is not None
    res = resolve_comparison(user_input="Сравни с матчем 15 апр", memories=[])
    assert res.is_comparison
    assert not res.found
    assert "15 апреля" in res.missing_message or "15" in res.missing_message
    assert any(a["id"] == "open_history" for a in res.chat_actions)


def test_resolve_found_with_date_in_memory():
    from datetime import date

    m = _mem(
        "match.2024-04-15",
        "Матч 15 апреля против Park M. — проигрыш 18-21 в решающем сете, слабая защита слева.",
    )
    m.event_date = date(2026, 4, 15)
    m.session_type = "match"
    memories = [m]
    res = resolve_comparison(
        user_input="Сравни с матчем 15 апр",
        memories=memories,
    )
    assert res.found
    assert res.grounding_context
    assert "15" in res.grounding_context or "апр" in res.grounding_context.lower()


def test_suggestions_fallback_without_history():
    out = build_suggestions_from_memories([])
    assert not any(s.lower().startswith("сравни с матчем") for s in out)
    assert any("тренировк" in s.lower() for s in out)


def test_suggestions_with_dated_match():
    memories = [_mem("match.log", "Итог матча 3 мая — победа 2:1.")]
    out = build_suggestions_from_memories(memories)
    assert any("3 мая" in s or "май" in s.lower() for s in out)
