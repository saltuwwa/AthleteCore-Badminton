"""Conservative pre-router: skip semantic_router LLM for obvious GENERAL_CHAT only."""

from __future__ import annotations

import re

from app.graph.semantic_router import (
    MemoryAction,
    RecommendedAgent,
    SemanticTurnDecision,
    TurnIntent,
    message_has_inline_facts,
)
from app.memory.past_event_intent import detect_past_event_signals

MAX_FAST_PATH_LEN = 120

# Whole-message or leading-phrase patterns (lowercase match after normalize).
_GENERAL_CHAT_RE = re.compile(
    r"^("
    r"привет[!.?\s]*|"
    r"здравствуй[те]*[!.?\s]*|"
    r"здаров[а]*[!.?\s]*|"
    r"hello[!.?\s]*|"
    r"hi[!.?\s]*|"
    r"как дела[?!.\s]*|"
    r"как ты[?!.\s]*|"
    r"как тебя зовут[?!.\s]*|"
    r"кто ты[?!.\s]*|"
    r"что ты умеешь[?!.\s]*|"
    r"чем можешь помочь[?!.\s]*|"
    r"что умеешь[?!.\s]*|"
    r"спасибо[!.?\s]*|"
    r"благодарю[!.?\s]*|"
    r"пока[!.?\s]*|"
    r"до свидания[!.?\s]*"
    r")$",
    re.IGNORECASE,
)

_IDENTITY_RE = re.compile(
    r"^(расскажи о себе|ты кто|ты — кто|what can you do)[!.?\s]*$",
    re.IGNORECASE,
)

_CALENDAR_MARKERS = (
    "расписан",
    "календар",
    "на неделю",
    "недельн",
    "план трен",
    "schedule",
    "перенеси трениров",
    "добавь в календар",
)

_HEALTH_MARKERS = (
    "травм",
    "болит",
    "подверн",
    "голеностоп",
    "устал",
    "восстанов",
    "сон ",
    "питани",
    "recovery",
    "health",
    "боль в",
)

_DATE_MARKERS = re.compile(
    r"(вчера|позавчера|завтра|"
    r"\d{1,2}\s*(го|ое|ая|ый|ого)\s*(янв|фев|мар|апр|мая|июн|июл|авг|сен|окт|ноя|дек)|"
    r"\d{4}-\d{2}-\d{2}|"
    r"\d+\s*км|"
    r"\d+\s*[:\-]\s*\d+)",
    re.IGNORECASE,
)

_DEICTIC_MARKERS = (
    "это ",
    "эту ",
    "этот ",
    "тогда ",
    "после этого",
    "после того",
    "тот матч",
    "та трениров",
    "та тренировка",
    "тот раз",
)

_SPORT_EVENT_MARKERS = (
    "матч",
    "тренир",
    "играла",
    "играл",
    "соперник",
    "подач",
    "раунд",
    "сет ",
    "match",
    "training",
    "ошиб",
    "разбери",
    "проанализ",
    "сравни",
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _has_sport_event_reference(t: str) -> bool:
    return any(m in t for m in _SPORT_EVENT_MARKERS)


def try_fast_path_general_chat(user_input: str) -> SemanticTurnDecision | None:
    """
    Return GENERAL_CHAT routing without LLM when message is clearly small talk / identity.
    Conservative: any doubt → None (caller uses semantic_router LLM).
    """
    text = _normalize(user_input)
    if not text or len(text) > MAX_FAST_PATH_LEN:
        return None

    t = text.lower()

    if message_has_inline_facts(text):
        return None
    if detect_past_event_signals(text):
        return None
    if _has_sport_event_reference(t):
        return None
    if any(m in t for m in _CALENDAR_MARKERS):
        return None
    if any(m in t for m in _HEALTH_MARKERS):
        return None
    if _DATE_MARKERS.search(t):
        return None
    if any(m in t for m in _DEICTIC_MARKERS):
        return None

    if not (_GENERAL_CHAT_RE.match(text) or _IDENTITY_RE.match(text)):
        return None

    return SemanticTurnDecision(
        turn_intent=TurnIntent.GENERAL_CHAT,
        memory_action=MemoryAction.NONE,
        recommended_agent=RecommendedAgent.DIRECT,
        reason="fast_path: obvious general chat",
    )
