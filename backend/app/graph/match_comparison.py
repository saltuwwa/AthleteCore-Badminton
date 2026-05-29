"""Resolve comparison requests against real LTM before Analyst generates prose."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, settings
from app.memory.models import Memory
from app.memory.recall_gating import cosine_similarity
from app.memory.retrieval import memory_scope_clause

ComparisonKind = Literal[
    "date",
    "last_match",
    "last_training",
    "opponent",
    "previous_session",
    "generic",
]

MONTH_ALIASES: dict[int, tuple[str, ...]] = {
    1: ("январ", "01.", "01 ", "01-"),
    2: ("феврал", "02.", "02 ", "02-"),
    3: ("март", "03.", "03 ", "03-"),
    4: ("апр", "04.", "04 ", "04-"),
    5: ("мая", "май", "05.", "05 ", "05-"),
    6: ("июн", "06.", "06 ", "06-"),
    7: ("июл", "07.", "07 ", "07-"),
    8: ("август", "08.", "08 ", "08-"),
    9: ("сентяб", "09.", "09 ", "09-"),
    10: ("октяб", "10.", "10 ", "10-"),
    11: ("нояб", "11.", "11 ", "11-"),
    12: ("декаб", "12.", "12 ", "12-"),
}

_COMPARISON_MARKERS = (
    "сравни",
    "сравнить",
    "сопостав",
    "в сравнении",
    "как я сыграл тогда",
    "как тогда",
    "в прошлый раз",
    "в прошлый",
    "с прошл",
    "с последн",
    "отличи от",
    "чем отличается",
    "compare",
)

_LAST_MATCH_MARKERS = (
    "последн",
    "прошлый матч",
    "прошлом матче",
    "предыдущий матч",
    "предыдущем матче",
)

_LAST_TRAINING_MARKERS = (
    "прошл",
    "предыдущ",
    "последн",
)

_EVENT_TYPES = frozenset(
    {"match_log", "training_log", "video_analysis", "competition_document_analysis"}
)


@dataclass(slots=True)
class ComparisonIntent:
    kind: ComparisonKind
    reference_label: str
    day: int | None = None
    month: int | None = None
    opponent: str | None = None


@dataclass(slots=True)
class ComparisonResolution:
    is_comparison: bool
    found: bool
    intent: ComparisonIntent | None = None
    reference_label: str | None = None
    confidence: float = 0.0
    grounding_context: str = ""
    missing_message: str = ""
    chat_actions: list[dict[str, str]] = field(default_factory=list)
    matched_memory_ids: list[str] = field(default_factory=list)


def is_comparison_query(text: str) -> bool:
    t = text.lower()
    return any(m in t for m in _COMPARISON_MARKERS)


def parse_comparison_intent(text: str) -> ComparisonIntent | None:
    if not is_comparison_query(text):
        return None
    t = text.lower()

    # Date: 15 апр, 15 апреля, 15.04.2024
    date_m = re.search(
        r"\b(\d{1,2})\s*(?:\.|/|-)?\s*(январ|феврал|март|апр|мая|май|июн|июл|август|сентяб|октяб|нояб|декаб|\d{1,2})",
        t,
    )
    if not date_m:
        date_m = re.search(
            r"(январ|феврал|март|апр|мая|май|июн|июл|август|сентяб|октяб|нояб|декаб)\w*\s+(\d{1,2})",
            t,
        )
        if date_m:
            month = _month_from_token(date_m.group(1))
            day = int(date_m.group(2))
            label = _date_label(day, month)
            return ComparisonIntent("date", f"матч за {label}", day=day, month=month)

    if date_m:
        day = int(date_m.group(1))
        month_token = date_m.group(2) if date_m.lastindex and date_m.lastindex >= 2 else ""
        month = _month_from_token(month_token) if month_token else None
        if month is None and month_token.isdigit():
            month = int(month_token)
        label = _date_label(day, month)
        return ComparisonIntent("date", f"матч за {label}", day=day, month=month)

    opp_m = re.search(
        r"(?:против|с)\s+([А-ЯЁA-Z][а-яёa-z]+(?:\s+[А-ЯЁA-Z][а-яёa-z]+)?)",
        text,
    )
    if opp_m:
        name = opp_m.group(1).strip()
        return ComparisonIntent(
            "opponent",
            f"матч против {name}",
            opponent=name,
        )

    if any(m in t for m in _LAST_MATCH_MARKERS) and "матч" in t:
        return ComparisonIntent("last_match", "последний матч")

    if any(m in t for m in _LAST_TRAINING_MARKERS) and "тренир" in t:
        return ComparisonIntent("last_training", "последняя тренировка")

    if "тогда" in t or "прошл" in t:
        return ComparisonIntent("previous_session", "прошлая сессия")

    return ComparisonIntent("generic", "указанное событие")


def _month_from_token(token: str) -> int | None:
    token = token.lower()
    for month, aliases in MONTH_ALIASES.items():
        if any(a in token for a in aliases[:1]):
            return month
    if token.isdigit():
        n = int(token)
        if 1 <= n <= 12:
            return n
    return None


def _date_label(day: int | None, month: int | None) -> str:
    months_ru = (
        "",
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    )
    if day and month and 1 <= month <= 12:
        return f"{day} {months_ru[month]}"
    if day:
        return f"{day} числа"
    return "указанную дату"


async def fetch_event_memories(
    session: AsyncSession,
    *,
    user_id: str | None,
    session_id: str,
    limit: int = 80,
) -> list[Memory]:
    scope = and_(Memory.active.is_(True), memory_scope_clause(user_id, session_id))
    stmt = (
        select(Memory)
        .where(
            scope,
            or_(
                Memory.event_type.in_(tuple(_EVENT_TYPES)),
                Memory.key.like("match.%"),
                Memory.key.like("training.%"),
            ),
        )
        .order_by(Memory.updated_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


def _memory_blob(m: Memory) -> str:
    return f"{m.key} {m.value}".lower()


def _mentions_date(m: Memory, day: int | None, month: int | None) -> bool:
    blob = _memory_blob(m)
    if day is not None:
        day_ok = (
            re.search(rf"\b{day}\b", blob) is not None
            or re.search(rf"\b{day:02d}\b", blob) is not None
            or re.search(rf"\b{day}\.", blob) is not None
        )
    else:
        day_ok = True
    if month is not None:
        month_ok = any(alias in blob for alias in MONTH_ALIASES[month])
    else:
        month_ok = True
    return day_ok and month_ok


def _mentions_opponent(m: Memory, opponent: str) -> bool:
    return opponent.lower() in _memory_blob(m)


def _is_match_memory(m: Memory) -> bool:
    if m.event_type == "match_log":
        return True
    k = m.key.lower()
    return k.startswith("match.") or "матч" in m.value.lower()[:200]


def _is_training_memory(m: Memory) -> bool:
    if m.event_type == "training_log":
        return True
    k = m.key.lower()
    return k.startswith("training.") or "трениров" in m.value.lower()[:200]


def _memory_label(m: Memory) -> str:
    k = m.key.replace("match.", "").replace("training.", "")
    snippet = m.value.strip().split("\n")[0][:120]
    if k and k not in ("latest", "log"):
        return f"{k}: {snippet}" if snippet else k
    return snippet or m.key


def _score_memory(
    m: Memory,
    intent: ComparisonIntent,
    query_embedding: list[float] | None,
    cfg: Settings,
) -> float:
    score = 0.0
    if intent.kind == "date" and _mentions_date(m, intent.day, intent.month):
        score = max(score, 0.92)
    if intent.kind == "opponent" and intent.opponent and _mentions_opponent(m, intent.opponent):
        score = max(score, 0.9)
    if intent.kind == "last_match" and (m.key == "match.latest" or _is_match_memory(m)):
        # Prefer explicit latest key, else recency handled externally
        score = max(score, 0.88 if m.key == "match.latest" else 0.55)
    if intent.kind == "last_training" and _is_training_memory(m):
        score = max(score, 0.85 if m.key.startswith("training.") else 0.5)
    if intent.kind in ("previous_session", "generic") and (
        _is_match_memory(m) or _is_training_memory(m)
    ):
        score = max(score, 0.45)

    if query_embedding and m.embedding:
        cos = cosine_similarity(query_embedding, m.embedding)
        if cos >= cfg.comparison_recall_min_cos:
            score = max(score, cos)

    return score


def resolve_comparison(
    *,
    user_input: str,
    memories: list[Memory],
    ranked_from_recall: list[tuple[Memory, float]] | None = None,
    query_embedding: list[float] | None = None,
    app_settings: Settings | None = None,
) -> ComparisonResolution:
    cfg = app_settings or settings
    intent = parse_comparison_intent(user_input)
    if intent is None:
        return ComparisonResolution(is_comparison=False, found=False)

    recall_map = {m.id: s for m, s in (ranked_from_recall or [])}
    candidates: list[tuple[Memory, float]] = []

    for m in memories:
        base = _score_memory(m, intent, query_embedding, cfg)
        if m.id in recall_map:
            base = max(base, recall_map[m.id])
        if base > 0:
            candidates.append((m, base))

    candidates.sort(key=lambda x: (x[1], x[0].updated_at or datetime.min.replace(tzinfo=UTC)), reverse=True)

    if intent.kind == "last_match":
        latest = [c for c in candidates if c[0].key == "match.latest"]
        if latest:
            candidates = latest + [c for c in candidates if c[0].key != "match.latest"]
        else:
            match_only = [(m, s) for m, s in candidates if _is_match_memory(m)]
            if match_only:
                candidates = match_only

    if intent.kind == "last_training":
        train_only = [(m, s) for m, s in candidates if _is_training_memory(m)]
        if train_only:
            candidates = train_only

    threshold = cfg.comparison_match_min_score
    top = candidates[0] if candidates else None

    if not top or top[1] < threshold:
        missing = (
            f"Я не нашёл в памяти {intent.reference_label}.\n"
            "Загрузи описание этого матча или выбери другой матч из истории — "
            "тогда я смогу сравнить."
        )
        actions = _not_found_actions(intent)
        return ComparisonResolution(
            is_comparison=True,
            found=False,
            intent=intent,
            reference_label=intent.reference_label,
            confidence=top[1] if top else 0.0,
            missing_message=missing,
            chat_actions=actions,
        )

    mem, conf = top
    label = _memory_label(mem)
    grounding = (
        "COMPARISON GROUNDING (verified in athlete memory — use ONLY these facts for the past event):\n"
        f"Reference: {intent.reference_label}\n"
        f"Matched record: {label}\n"
        f"Key: {mem.key}\n"
        f"Content:\n{mem.value.strip()}\n"
        "Do NOT invent scores, opponents, fatigue, tactics, or errors not stated above."
    )

    return ComparisonResolution(
        is_comparison=True,
        found=True,
        intent=intent,
        reference_label=label,
        confidence=conf,
        grounding_context=grounding,
        matched_memory_ids=[str(mem.id)],
    )


def _not_found_actions(intent: ComparisonIntent) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = [
        {"id": "open_history", "label": "Открыть историю", "href": "/history"},
    ]
    if intent.kind == "date" and intent.day and intent.month:
        months_short = (
            "",
            "янв",
            "фев",
            "мар",
            "апр",
            "мая",
            "июн",
            "июл",
            "авг",
            "сен",
            "окт",
            "ноя",
            "дек",
        )
        short = f"{intent.day} {months_short[intent.month]}"
        actions.append(
            {
                "id": "add_match",
                "label": f"Добавить матч {short}",
                "prefill": f"Матч {intent.day} {months_short[intent.month]}: ",
            }
        )
    else:
        actions.append(
            {
                "id": "add_match",
                "label": "Добавить описание матча",
                "prefill": "Матч: ",
            }
        )
    return actions


def build_comparison_not_found_reply(resolution: ComparisonResolution) -> str:
    return resolution.missing_message


def build_suggestions_from_memories(memories: list[Memory]) -> list[str]:
    """Chat input chips grounded in real LTM."""
    suggestions: list[str] = []
    seen: set[str] = set()

    for m in memories:
        if not (_is_match_memory(m) or _is_training_memory(m)):
            continue
        if m.event_date:
            months_ru = (
                "",
                "янв",
                "фев",
                "мар",
                "апр",
                "мая",
                "июн",
                "июл",
                "авг",
                "сен",
                "окт",
                "ноя",
                "дек",
            )
            label = f"{m.event_date.day} {months_ru[m.event_date.month]}"
            phrase = f"Сравни с матчем {label}"
            key = phrase.lower()
            if key not in seen:
                seen.add(key)
                suggestions.append(phrase)
            if len(suggestions) >= 3:
                return suggestions
        blob = _memory_blob(m)
        for day, month in _extract_dates_from_blob(blob):
            label = _date_label(day, month)
            phrase = f"Сравни с матчем {label}"
            key = phrase.lower()
            if key not in seen:
                seen.add(key)
                suggestions.append(phrase)
            if len(suggestions) >= 3:
                return suggestions

    if memories and _is_match_memory(memories[0]):
        suggestions.append("Сравни с последним матчем")

    if not suggestions:
        return [
            "Разбери мою последнюю тренировку",
            "Помоги найти ошибки в матче",
            "Составь план восстановления",
            "Что улучшить перед следующим матчем?",
        ]

    defaults = [
        "Разбери ошибки 2-го сета",
        "Сгенерируй план восстановления",
    ]
    for d in defaults:
        if len(suggestions) >= 3:
            break
        if d.lower() not in seen:
            suggestions.append(d)
    return suggestions[:3]


def _extract_dates_from_blob(blob: str) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for m in re.finditer(
        r"\b(\d{1,2})\s*(январ|феврал|март|апр|мая|май|июн|июл|август|сентяб|октяб|нояб|декаб)",
        blob,
    ):
        day = int(m.group(1))
        month = _month_from_token(m.group(2))
        if month:
            out.append((day, month))
    return out
