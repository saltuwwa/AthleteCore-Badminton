"""Fast path pre-router — skip semantic_router LLM for obvious GENERAL_CHAT."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.graph.fast_path_general_chat import try_fast_path_general_chat
from app.graph.semantic_router import TurnIntent, route_user_turn


def test_try_fast_path_matches_small_talk():
    d = try_fast_path_general_chat("как дела?")
    assert d is not None
    assert d.turn_intent == TurnIntent.GENERAL_CHAT


def test_try_fast_path_rejects_training_log():
    assert try_fast_path_general_chat("вчера была тренировка: бег 5 км") is None


def test_try_fast_path_rejects_past_lookup():
    assert try_fast_path_general_chat("разбери мою тренировку 28 мая") is None


@pytest.mark.asyncio
async def test_route_user_turn_fast_path_skips_llm():
    with patch("app.graph.semantic_router.acompletion", new_callable=AsyncMock) as mock_llm:
        decision = await route_user_turn("как дела?", reference=date(2026, 5, 29))
    mock_llm.assert_not_called()
    assert decision.turn_intent == TurnIntent.GENERAL_CHAT
    assert (decision.date_normalization or {}).get("route_source") == "fast_path_general_chat"
