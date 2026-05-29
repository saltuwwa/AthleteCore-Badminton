"""Methodology RAG gating for analyst context."""

from app.graph.methodology_gate import needs_methodology_rag
from app.graph.semantic_router import TurnIntent


def test_skip_methodology_for_grounded_past_recap():
    use, reason = needs_methodology_rag(
        "разбери мою тренировку которая была 28го мая",
        turn_intent=TurnIntent.PAST_EVENT_LOOKUP_REQUEST.value,
        past_event_found=True,
    )
    assert use is False
    assert reason == "past_event_grounded_recap"


def test_use_methodology_for_advice():
    use, reason = needs_methodology_rag(
        "как восстановиться после травмы?",
        turn_intent=TurnIntent.ADVICE_REQUEST.value,
        past_event_found=False,
    )
    assert use is True
    assert reason is None
