"""Structured detection of past sport-event requests (read-path intent, not regex soup)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class PastEventAction(str, Enum):
    ANALYZE = "analyze"
    COMPARE = "compare"
    RECALL = "recall"
    FIND_ERRORS = "find_errors"
    ASSESS_PROGRESS = "assess_progress"


class PastEventTimeRef(str, Enum):
    LAST = "last"
    PREVIOUS = "previous"
    RELATIVE_DAY = "relative_day"
    CALENDAR_DATE = "calendar_date"
    VAGUE_PAST = "vague_past"


class PastEventSubject(str, Enum):
    TRAINING = "training"
    MATCH = "match"
    GAME = "game"
    ANY = "any"


@dataclass(frozen=True, slots=True)
class PastEventSignals:
    """Layered intent signals parsed from user text."""

    actions: frozenset[PastEventAction]
    time_refs: frozenset[PastEventTimeRef]
    subject: PastEventSubject
    raw_lower: str


# --- marker lexicons (structured lists, shared with guard) ----------------------------

COMPARE_MARKERS: tuple[str, ...] = (
    "сравни",
    "сравнить",
    "сопостав",
    "отличи от",
    "чем отличается",
    "compare",
    "с предыдущ",
    "с прошл",
    "с последн",
)

ANALYZE_MARKERS: tuple[str, ...] = (
    "разбери",
    "разобрать",
    "проанализируй",
    "проанализировать",
    "анализ ",
    "analyze",
    "break down",
)

RECALL_MARKERS: tuple[str, ...] = (
    "вспомни",
    "вспомнить",
    "напомни",
    "что было",
    "как тогда",
    "как я сыграл",
)

ERROR_REVIEW_MARKERS: tuple[str, ...] = (
    "найди ошиб",
    "найти ошиб",
    "ошибк в последн",
    "ошибк в прошл",
    "find error",
    "mistakes in",
)

PROGRESS_MARKERS: tuple[str, ...] = (
    "прогресс",
    "оцени прогресс",
    "оценить прогресс",
    "progress",
    "улучшил",
    "стал лучше",
)

TEMPORAL_MARKERS: tuple[str, ...] = (
    "последн",
    "прошл",
    "предыдущ",
    "вчера",
    "позавчера",
    "тогда",
    "на прошлой неделе",
    "прошлой неделе",
    "тот матч",
    "та тренировка",
)

TRAINING_MARKERS: tuple[str, ...] = (
    "трениров",
    "workout",
    "practice session",
)

MATCH_MARKERS: tuple[str, ...] = (
    "матч",
    "match",
    "игр",
    "game",
    "соревнован",
    "турнир",
)


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(m in text for m in markers)


def _detect_actions(text: str) -> frozenset[PastEventAction]:
    found: set[PastEventAction] = set()
    if _contains_any(text, COMPARE_MARKERS):
        found.add(PastEventAction.COMPARE)
    if _contains_any(text, ANALYZE_MARKERS):
        found.add(PastEventAction.ANALYZE)
    if _contains_any(text, RECALL_MARKERS):
        found.add(PastEventAction.RECALL)
    if _contains_any(text, ERROR_REVIEW_MARKERS):
        found.add(PastEventAction.FIND_ERRORS)
    if _contains_any(text, PROGRESS_MARKERS):
        found.add(PastEventAction.ASSESS_PROGRESS)
    return frozenset(found)


def _detect_time_refs(text: str) -> frozenset[PastEventTimeRef]:
    found: set[PastEventTimeRef] = set()
    if _contains_any(text, ("последн", "last ")):
        found.add(PastEventTimeRef.LAST)
    if _contains_any(text, ("прошл", "предыдущ", "previous", "before")):
        found.add(PastEventTimeRef.PREVIOUS)
    if _contains_any(text, ("вчера", "позавчера", "yesterday", "last week")):
        found.add(PastEventTimeRef.RELATIVE_DAY)
    if re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text):
        found.add(PastEventTimeRef.CALENDAR_DATE)
    if re.search(
        r"\b(\d{1,2})\s*(январ|феврал|март|апр|мая|май|июн|июл|август|сентяб|октяб|нояб|декаб)",
        text,
    ):
        found.add(PastEventTimeRef.CALENDAR_DATE)
    if _contains_any(text, ("тогда", "что было", "как тогда")):
        found.add(PastEventTimeRef.VAGUE_PAST)
    return frozenset(found)


def _detect_subject(text: str) -> PastEventSubject:
    if _contains_any(text, TRAINING_MARKERS):
        return PastEventSubject.TRAINING
    if _contains_any(text, MATCH_MARKERS):
        return PastEventSubject.MATCH
    if "игр" in text or "game" in text:
        return PastEventSubject.GAME
    return PastEventSubject.ANY


def detect_past_event_signals(user_input: str) -> PastEventSignals | None:
    """
    True when the message semantically asks about a past sport event in memory.

    Requires at least one action (analyze / compare / recall / errors / progress)
    OR a clear temporal+subject pairing (e.g. «последняя тренировка»).
    """
    text = (user_input or "").strip().lower()
    if not text:
        return None

    actions = _detect_actions(text)
    time_refs = _detect_time_refs(text)
    subject = _detect_subject(text)

    has_action = bool(actions)
    has_temporal = bool(time_refs)
    has_subject = subject != PastEventSubject.ANY

    # «Разбери мою последнюю тренировку» — analyze + temporal + subject
    if has_action and (has_temporal or has_subject):
        return PastEventSignals(actions, time_refs, subject, text)

    # «последняя тренировка» / «прошлый матч» without explicit analyze verb
    if has_temporal and has_subject:
        return PastEventSignals(
            actions or frozenset({PastEventAction.ANALYZE}),
            time_refs,
            subject,
            text,
        )

    # «сравни с предыдущим» — compare + vague past
    if PastEventAction.COMPARE in actions and has_temporal:
        return PastEventSignals(actions, time_refs, subject, text)

    # «оценить прогресс по прошлым данным»
    if PastEventAction.ASSESS_PROGRESS in actions and has_temporal:
        return PastEventSignals(actions, time_refs, subject, text)

    # Calendar date mention + sport context
    if PastEventTimeRef.CALENDAR_DATE in time_refs and (
        has_subject or has_action
    ):
        return PastEventSignals(
            actions or frozenset({PastEventAction.ANALYZE}),
            time_refs,
            subject,
            text,
        )

    return None


def is_past_event_request(user_input: str) -> bool:
    return detect_past_event_signals(user_input) is not None
