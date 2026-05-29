"""Resolve past-event queries: inline facts → structured SQL → semantic fallback → honest not-found."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, settings
from app.memory.date_normalizer import normalize_relative_event_dates, parse_absolute_date_in_text
from app.memory.memory_classification import has_episodic_substance
from app.memory.past_event_intent import (
    PastEventAction,
    PastEventSubject,
    PastEventTimeRef,
    detect_past_event_signals,
    is_past_event_request,
)
from app.memory.recall_gating import cosine_similarity
from app.memory.structured_retrieval import (
    CONF_LAST_NULL_DATE_FALLBACK,
    StructuredMatch,
    find_by_opponent,
    find_last_match,
    find_last_training,
    find_match_by_date,
    find_match_by_day_month,
    find_training_by_date,
    format_grounding_block,
)

from .constants import SESSION_MATCH, SESSION_TRAINING
from .date_normalizer import (
    DEFAULT_MEMORY_TIMEZONE,
    DateResolutionResult,
    normalize_memory_event_dates,
    reference_local_date,
    resolve_memory_timezone,
)
from .models import Memory
from .retrieval import memory_scope_clause
from .retrieval_trace import (
    RetrievedMemoryTraceItem,
    format_memory_query_for_intent,
    memory_row_to_trace_item,
)

PastIntentKind = Literal[
    "compare",
    "last_training",
    "last_match",
    "date",
    "opponent",
    "relative_day",
    "analyze_past",
    "progress_review",
    "none",
]

EventFocus = Literal["match", "training", "auto"]


@dataclass(slots=True)
class PastEventIntent:
    kind: PastIntentKind
    reference_label: str
    day: int | None = None
    month: int | None = None
    opponent: str | None = None
    target_date: date | None = None
    event_focus: EventFocus = "auto"
    requires_grounding: bool = False


@dataclass(slots=True)
class PastEventRetrievalTrace:
    memory_query: str = ""
    structured_retrieval_used: bool = False
    structured_function_called: str | None = None
    semantic_fallback_used: bool = False
    structured_match_reason: str | None = None
    retrieved_memory_items: list[RetrievedMemoryTraceItem] = field(default_factory=list)
    confidence_score: float = 0.0
    similarity_score: float | None = None
    event_date_parsed: str | None = None
    date_normalization_reason: str | None = None
    blocked_reason: str | None = None


_INTENTS_REQUIRING_KNOWN_EVENT_DATE = frozenset(
    {"last_training", "last_match", "date", "relative_day", "compare", "analyze_past", "progress_review"}
)


@dataclass(slots=True)
class PastEventResolution:
    is_past_event_query: bool
    found: bool
    intent: PastEventIntent | None = None
    reference_label: str | None = None
    confidence: float = 0.0
    grounding_context: str = ""
    missing_message: str = ""
    chat_actions: list[dict[str, str]] = field(default_factory=list)
    matched_memory_ids: list[str] = field(default_factory=list)
    inline_facts_in_message: bool = False
    llm_allowed: bool = True
    retrieval: PastEventRetrievalTrace = field(default_factory=PastEventRetrievalTrace)

    @property
    def is_past_event_request(self) -> bool:
        return self.is_past_event_query


def needs_past_event_grounding(user_input: str) -> bool:
    """Whether Analyst must ground on a stored past event before generating analysis."""
    return is_past_event_request(user_input)


def _has_inline_episodic_facts(user_input: str) -> bool:
    """Concrete log in the message (scores, RPE, duration, opponent) — not a bare analyze request."""
    t = user_input.lower()
    if re.search(r"\brpe\s*[:\s-]?\s*\d", t):
        return True
    if re.search(r"\d+\s*(мин|минут|min)", t):
        return True
    if re.search(r"\d+\s*[:\-]\s*\d+", t):
        return True
    has_concrete_marker = bool(
        re.search(r"\d", t)
        or re.search(r"\brpe\b", t)
        or "против " in t
        or " vs " in t
        or "соперник" in t
        or "очки" in t
    )
    if re.search(r"\b(устал[аи]?|устала)\b", t):
        return True
    if re.search(r"\b(обыграл[аи]?|проиграл[аи]?|победил[аи]?)\b", t):
        return has_concrete_marker
    if any(p in t for p in ("против ", " vs ", "соперник", "очки")):
        return True
    if len(t) > 90 and t.count(",") >= 2:
        return has_episodic_substance({"value": user_input, "facts": {}})
    return False


def user_provided_facts_in_message(user_input: str) -> bool:
    """Athlete described concrete sport facts in this turn (no DB lookup required)."""
    text = (user_input or "").strip()
    if not text:
        return False
    if is_past_event_request(text):
        return _has_inline_episodic_facts(text)
    return has_episodic_substance({"value": text, "facts": {}})


def format_inline_message_grounding(user_input: str, *, reference_label: str) -> str:
    return (
        "PAST EVENT GROUNDING (facts from the athlete's CURRENT message — use ONLY these):\n"
        f"Reference: {reference_label}\n"
        f"Athlete message:\n{user_input.strip()}\n"
        "Do NOT invent scores, opponents, fatigue, tactics, or errors not stated above."
    )


def parse_past_event_intent(
    user_input: str,
    reference: date,
    *,
    timezone: str = DEFAULT_MEMORY_TIMEZONE,
) -> PastEventIntent | None:
    signals = detect_past_event_signals(user_input)
    if signals is None:
        return None

    calendar = normalize_memory_event_dates(
        user_input,
        reference_datetime=reference,
        timezone=timezone,
    )

    t = signals.raw_lower
    is_compare = PastEventAction.COMPARE in signals.actions

    if calendar.resolved and calendar.event_date and not calendar.needs_clarification:
        focus: EventFocus = "auto"
        if signals.subject == PastEventSubject.TRAINING:
            focus = "training"
        elif signals.subject in (PastEventSubject.MATCH, PastEventSubject.GAME):
            focus = "match"
        label = f"событие от {calendar.event_date.isoformat()}"
        if calendar.event_date_end and calendar.event_date_end != calendar.event_date:
            label = (
                f"события {calendar.event_date.isoformat()}–"
                f"{calendar.event_date_end.isoformat()}"
            )
        return PastEventIntent(
            "date" if not is_compare else "compare",
            label,
            target_date=calendar.event_date,
            event_focus=focus,
            requires_grounding=True,
        )

    if signals.subject == PastEventSubject.TRAINING and (
        PastEventTimeRef.LAST in signals.time_refs
        or "последн" in t
        or "вчера" in t
        or "позавчера" in t
    ):
        return PastEventIntent(
            "last_training" if not is_compare else "compare",
            "последняя тренировка",
            event_focus="training",
            requires_grounding=True,
        )

    if signals.subject in (PastEventSubject.MATCH, PastEventSubject.GAME) and (
        PastEventTimeRef.LAST in signals.time_refs or "последн" in t or "прошл" in t
    ):
        return PastEventIntent(
            "last_match" if not is_compare else "compare",
            "последний матч",
            event_focus="match",
            requires_grounding=True,
        )

    rel_start, _ = normalize_relative_event_dates(user_input, reference)
    if rel_start:
        focus: EventFocus = "auto"
        if signals.subject == PastEventSubject.TRAINING:
            focus = "training"
            label = f"тренировка от {rel_start.isoformat()}"
        elif signals.subject in (PastEventSubject.MATCH, PastEventSubject.GAME):
            focus = "match"
            label = f"матч от {rel_start.isoformat()}"
        else:
            label = f"событие от {rel_start.isoformat()}"
        return PastEventIntent(
            "relative_day" if not is_compare else "compare",
            label,
            target_date=rel_start,
            event_focus=focus,
            requires_grounding=True,
        )

    opp_m = re.search(
        r"(?:против|с)\s+([А-ЯЁA-Z][а-яёa-z]+(?:\s+[А-ЯЁA-Z][а-яёa-z]+)?)",
        user_input,
    )
    if opp_m:
        name = opp_m.group(1).strip()
        return PastEventIntent(
            "opponent" if not is_compare else "compare",
            f"матч против {name}",
            opponent=name,
            event_focus="match",
            requires_grounding=True,
        )

    if PastEventAction.ASSESS_PROGRESS in signals.actions:
        return PastEventIntent(
            "progress_review" if not is_compare else "compare",
            "прогресс по прошлым данным",
            event_focus="auto",
            requires_grounding=True,
        )

    if PastEventAction.FIND_ERRORS in signals.actions:
        focus: EventFocus = "match" if signals.subject in (
            PastEventSubject.MATCH,
            PastEventSubject.GAME,
        ) else "auto"
        kind: PastIntentKind = "last_match" if focus == "match" else "analyze_past"
        label = "последняя игра" if focus == "match" else "прошлое событие"
        return PastEventIntent(kind, label, event_focus=focus, requires_grounding=True)

    if signals.actions & {
        PastEventAction.ANALYZE,
        PastEventAction.RECALL,
        PastEventAction.COMPARE,
    }:
        focus = (
            "training"
            if signals.subject == PastEventSubject.TRAINING
            else ("match" if signals.subject in (PastEventSubject.MATCH, PastEventSubject.GAME) else "auto")
        )
        kind = "analyze_past" if not is_compare else "compare"
        if focus == "training" and PastEventTimeRef.LAST in signals.time_refs:
            kind = "last_training"
        if focus == "match" and PastEventTimeRef.LAST in signals.time_refs:
            kind = "last_match"
        return PastEventIntent(
            kind,
            "прошлое спортивное событие",
            event_focus=focus,
            requires_grounding=True,
        )

    if is_compare:
        return PastEventIntent(
            "compare",
            "указанное событие",
            event_focus="auto",
            requires_grounding=True,
        )

    return None


def _month_name(month: int) -> str:
    names = (
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
    return names[month] if 1 <= month <= 12 else ""


async def _lookup_by_date(
    db: AsyncSession,
    intent: PastEventIntent,
    *,
    user_id: str | None,
    session_id: str,
    target: date,
) -> StructuredMatch | None:
    if intent.event_focus == "training":
        return await find_training_by_date(db, user_id, target, session_id=session_id)
    if intent.event_focus == "match":
        return await find_match_by_date(db, user_id, target, session_id=session_id)
    hit = await find_match_by_date(db, user_id, target, session_id=session_id)
    if hit:
        return hit
    return await find_training_by_date(db, user_id, target, session_id=session_id)


def structured_function_for_intent(intent: PastEventIntent) -> str | None:
    """Name of the primary SQL helper invoked for this intent (dev trace + tests)."""
    if intent.kind == "last_training":
        return "find_last_training"
    if intent.kind == "last_match":
        return "find_last_match"
    if intent.target_date:
        if intent.event_focus == "training":
            return "find_training_by_date"
        if intent.event_focus == "match":
            return "find_match_by_date"
        return "find_match_or_training_by_date"
    if intent.day and intent.month:
        return "find_match_by_day_month"
    if intent.opponent:
        return "find_by_opponent"
    if intent.kind in ("analyze_past", "progress_review", "compare"):
        if intent.event_focus == "training":
            return "find_last_training"
        if intent.event_focus == "match":
            return "find_last_match"
        return "find_last_training_or_match"
    return None


def _requires_exact_episodic_match(intent: PastEventIntent, user_input: str) -> bool:
    """Dated / last-event requests must not use semantic fallback or generic hybrid memory."""
    if intent.target_date or (intent.day and intent.month):
        return True
    if intent.kind in ("last_training", "last_match", "date", "relative_day"):
        return True
    if _mentions_calendar_date_without_resolution(intent, user_input):
        return True
    return False


def _mentions_calendar_date_without_resolution(intent: PastEventIntent, user_input: str) -> bool:
    """User cited a day+month but we failed to bind target_date — do not fall back to «last» event."""
    if intent.target_date or (intent.day and intent.month):
        return False
    t = user_input.lower()
    return bool(
        re.search(
            r"\d{1,2}(?:-?го|-?е)?\s*(?:\.|/|-)?\s*"
            r"(январ|феврал|март|апр|мая|май|июн|июл|август|сентяб|октяб|нояб|декаб)",
            t,
        )
    )


async def _lookup_day_month(
    db: AsyncSession,
    intent: PastEventIntent,
    *,
    user_id: str | None,
    session_id: str,
    reference: date,
) -> StructuredMatch | None:
    if intent.event_focus == "training":
        years = [reference.year, reference.year - 1, reference.year - 2]
        for year in years:
            try:
                target = date(year, intent.month, intent.day)  # type: ignore[arg-type]
            except (ValueError, TypeError):
                continue
            hit = await find_training_by_date(
                db, user_id, target, session_id=session_id
            )
            if hit:
                hit.match_reason = f"structured:training_day_month:{target.isoformat()}"
                return hit
        return None
    return await find_match_by_day_month(
        db,
        user_id,
        day=intent.day,  # type: ignore[arg-type]
        month=intent.month,  # type: ignore[arg-type]
        reference=reference,
        session_id=session_id,
    )


async def _structured_lookup(
    db: AsyncSession,
    intent: PastEventIntent,
    *,
    user_id: str | None,
    session_id: str,
    reference: date,
    user_input: str = "",
) -> StructuredMatch | None:
    import time

    from app.graph.latency_trace import current_latency_trace, stage_span

    fn = structured_function_for_intent(intent) or f"intent_{intent.kind}"
    with stage_span("structured_retrieval"):
        t0 = time.perf_counter()
        result = await _structured_lookup_impl(
            db,
            intent,
            user_id=user_id,
            session_id=session_id,
            reference=reference,
            user_input=user_input,
        )
        duration_ms = (time.perf_counter() - t0) * 1000
    trace = current_latency_trace()
    if trace:
        rows = 1 if result and result.memory is not None else 0
        trace.record_db_call(name=fn, duration_ms=duration_ms, rows=rows)
    return result


async def _structured_lookup_impl(
    db: AsyncSession,
    intent: PastEventIntent,
    *,
    user_id: str | None,
    session_id: str,
    reference: date,
    user_input: str = "",
) -> StructuredMatch | None:
    if intent.kind == "last_training":
        return await find_last_training(db, user_id, session_id=session_id)
    if intent.kind == "last_match":
        return await find_last_match(db, user_id, session_id=session_id)
    if intent.target_date:
        return await _lookup_by_date(
            db,
            intent,
            user_id=user_id,
            session_id=session_id,
            target=intent.target_date,
        )
    if intent.day and intent.month:
        return await _lookup_day_month(
            db,
            intent,
            user_id=user_id,
            session_id=session_id,
            reference=reference,
        )
    if intent.opponent:
        return await find_by_opponent(db, user_id, intent.opponent, session_id=session_id)
    if intent.kind in ("analyze_past", "progress_review"):
        if _mentions_calendar_date_without_resolution(intent, user_input):
            return None
        if intent.event_focus == "training":
            return await find_last_training(db, user_id, session_id=session_id)
        if intent.event_focus == "match":
            return await find_last_match(db, user_id, session_id=session_id)
        hit = await find_last_training(db, user_id, session_id=session_id)
        if hit:
            return hit
        return await find_last_match(db, user_id, session_id=session_id)
    if intent.kind == "compare":
        if intent.event_focus == "training":
            return await find_last_training(db, user_id, session_id=session_id)
        return await find_last_match(db, user_id, session_id=session_id)
    return None


async def _semantic_fallback(
    db: AsyncSession,
    *,
    user_input: str,
    user_id: str | None,
    session_id: str,
    intent: PastEventIntent,
    query_embedding: list[float] | None,
    cfg: Settings,
) -> tuple[Memory | None, float]:
    from sqlalchemy import and_, or_, select

    scope = and_(Memory.active.is_(True), memory_scope_clause(user_id, session_id))
    filters = []
    if intent.kind in ("last_training", "analyze_past", "progress_review") or (
        intent.event_focus == "training"
    ):
        filters.append(
            or_(
                Memory.session_type == SESSION_TRAINING,
                Memory.event_type == "training_log",
            )
        )
    elif intent.kind in ("last_match", "compare", "date", "opponent") or intent.event_focus == "match":
        filters.append(
            or_(
                Memory.session_type == SESSION_MATCH,
                Memory.event_type == "match_log",
                Memory.key.like("match.%"),
            )
        )

    cond = scope
    if filters:
        cond = and_(scope, or_(*filters))
    stmt = (
        select(Memory)
        .where(cond, Memory.event_date.isnot(None))
        .order_by(Memory.event_date.desc(), Memory.created_at.desc())
        .limit(40)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    if not rows:
        return None, 0.0

    best: tuple[Memory, float] | None = None
    for m in rows:
        score = 0.0
        if m.event_date and intent.target_date and m.event_date == intent.target_date:
            score = 0.95
        if query_embedding and m.embedding:
            score = max(score, cosine_similarity(query_embedding, m.embedding))
        if score > 0 and (best is None or score > best[1]):
            best = (m, score)

    if best and best[1] >= cfg.comparison_recall_min_cos:
        return best
    return None, 0.0


def _not_found_message(intent: PastEventIntent) -> str:
    if intent.target_date and intent.event_focus == "training":
        return (
            f"Я не нашёл сохранённую тренировку за {intent.target_date.day} "
            f"{_month_name(intent.target_date.month)} {intent.target_date.year}. "
            "Опиши тренировку здесь или добавь её в историю — тогда смогу разобрать ошибки."
        )
    if intent.target_date and intent.event_focus == "match":
        return (
            f"Я не нашёл сохранённый матч за {intent.target_date.day} "
            f"{_month_name(intent.target_date.month)} {intent.target_date.year}. "
            "Опиши матч в сообщении или добавь его в историю."
        )
    if intent.day and intent.month and intent.event_focus == "training":
        return (
            f"Я не нашёл сохранённую тренировку за {intent.day} {_month_name(intent.month)}. "
            "Опиши тренировку здесь или добавь её в историю."
        )
    if intent.kind == "last_training" or (
        intent.event_focus == "training" and intent.kind == "analyze_past"
    ):
        return (
            "Я не нашёл сохранённую последнюю тренировку. "
            "Опиши тренировку здесь или добавь её в историю — тогда я смогу разобрать ошибки."
        )
    if intent.kind == "last_match" or intent.event_focus == "match":
        return (
            "Я не нашёл сохранённый последний матч. "
            "Опиши матч в сообщении или добавь его в историю — тогда смогу дать точный разбор."
        )
    if intent.kind == "progress_review":
        return (
            "Я не нашёл в памяти прошлые тренировки или матчи для оценки прогресса. "
            "Добавь описания событий в историю или расскажи о них здесь."
        )
    return (
        f"Я не нашёл в памяти {intent.reference_label}.\n"
        "Опиши событие в этом сообщении или добавь его в историю — "
        "тогда смогу дать точный разбор без догадок."
    )


def _not_found_actions(intent: PastEventIntent) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = [
        {"id": "open_history", "label": "Открыть историю", "href": "/history"},
    ]
    if intent.day and intent.month:
        months_short = ("", "янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек")
        short = f"{intent.day} {months_short[intent.month]}"
        actions.append(
            {
                "id": "add_match",
                "label": f"Добавить матч {short}",
                "prefill": f"Матч {intent.day} {months_short[intent.month]}: ",
            }
        )
    else:
        label = (
            "тренировку"
            if intent.kind == "last_training" or intent.event_focus == "training"
            else "матч"
        )
        actions.append(
            {
                "id": "add_event",
                "label": f"Добавить описание ({label})",
                "prefill": f"{label.capitalize()}: ",
            }
        )
    return actions


def _date_resolution_for_text(
    user_input: str,
    reference: date,
    *,
    timezone: str = DEFAULT_MEMORY_TIMEZONE,
) -> DateResolutionResult:
    return normalize_memory_event_dates(
        user_input,
        reference_datetime=reference,
        timezone=timezone,
    )


async def resolve_past_event(
    db: AsyncSession,
    *,
    user_input: str,
    user_id: str | None,
    session_id: str,
    reference: date | None = None,
    query_embedding: list[float] | None = None,
    app_settings: Settings | None = None,
) -> PastEventResolution:
    """
    Past-event read path:
    1. Detect past-event request
    2. If athlete provided facts in this message → allow LLM with inline grounding
    3. Else structured SQL → semantic fallback
    4. If still not found → block LLM (honest not-found)
    """
    cfg = app_settings or settings
    tz = resolve_memory_timezone(app_timezone=cfg.memory_timezone)
    ref = reference or reference_local_date(timezone=tz)
    intent = parse_past_event_intent(user_input, ref, timezone=tz)
    if intent is None:
        return PastEventResolution(is_past_event_query=False, found=False, llm_allowed=True)

    from app.graph.latency_trace import stage_span

    with stage_span("date_normalizer"):
        date_res = _date_resolution_for_text(user_input, ref, timezone=tz)
    if date_res.needs_clarification:
        return PastEventResolution(
            is_past_event_query=True,
            found=False,
            intent=intent,
            reference_label=intent.reference_label,
            llm_allowed=False,
            missing_message=date_res.clarification_message
            or "Уточни дату события.",
            retrieval=PastEventRetrievalTrace(
                memory_query=user_input[:500],
                blocked_reason="invalid_calendar_date",
                date_normalization_reason=date_res.date_resolution_reason,
            ),
        )

    date_parsed = date_res.event_date.isoformat() if date_res.event_date else None
    date_reason = date_res.date_resolution_reason
    retrieval = PastEventRetrievalTrace(
        memory_query=format_memory_query_for_intent(
            user_input,
            kind=intent.kind,
            reference_label=intent.reference_label,
            target_date_iso=intent.target_date.isoformat() if intent.target_date else None,
            opponent=intent.opponent,
        ),
        event_date_parsed=date_parsed or (intent.target_date.isoformat() if intent.target_date else None),
        date_normalization_reason=date_reason,
    )

    if user_provided_facts_in_message(user_input):
        return PastEventResolution(
            is_past_event_query=True,
            found=True,
            intent=intent,
            reference_label="описание в текущем сообщении",
            confidence=1.0,
            grounding_context=format_inline_message_grounding(
                user_input, reference_label=intent.reference_label
            ),
            inline_facts_in_message=True,
            llm_allowed=True,
            retrieval=retrieval,
        )

    retrieval.structured_function_called = structured_function_for_intent(intent)
    if retrieval.structured_function_called:
        retrieval.structured_retrieval_used = True
    structured = await _structured_lookup(
        db,
        intent,
        user_id=user_id,
        session_id=session_id,
        reference=ref,
        user_input=user_input,
    )
    confidence = structured.confidence if structured else 0.0
    memory = structured.memory if structured else None
    semantic_used = False
    sem_score: float | None = None

    if structured:
        retrieval.structured_match_reason = structured.match_reason
        retrieval.confidence_score = structured.confidence
        retrieval.retrieved_memory_items = [
            memory_row_to_trace_item(
                structured.memory,
                match_reason=structured.match_reason,
            )
        ]
        if (
            memory.event_date is None
            and structured.confidence == CONF_LAST_NULL_DATE_FALLBACK
            and intent.kind in _INTENTS_REQUIRING_KNOWN_EVENT_DATE
        ):
            retrieval.blocked_reason = "pending_event_date_unknown"
            retrieval.date_normalization_reason = (
                retrieval.date_normalization_reason or "event_date_unknown"
            )
            memory = None
            confidence = 0.0

    if memory is None:
        from app.memory.pending_write import pending_grounding_for_lookup

        pending_ctx = pending_grounding_for_lookup(
            user_id, session_id, intent, user_input=user_input
        )
        if pending_ctx:
            retrieval.retrieved_memory_items = [
                {
                    "source": "pending_write",
                    "match_reason": "pending_memory_write",
                }
            ]
            return PastEventResolution(
                is_past_event_query=True,
                found=True,
                intent=intent,
                reference_label="событие из недавнего сообщения (сохраняется)",
                confidence=0.95,
                grounding_context=pending_ctx,
                inline_facts_in_message=True,
                llm_allowed=True,
                retrieval=retrieval,
            )

    if memory is None and not _requires_exact_episodic_match(intent, user_input):
        with stage_span("memory_recall"):
            mem2, sem_score = await _semantic_fallback(
                db,
                user_input=user_input,
                user_id=user_id,
                session_id=session_id,
                intent=intent,
                query_embedding=query_embedding,
                cfg=cfg,
            )
        if mem2:
            memory = mem2
            confidence = sem_score
            semantic_used = True
            retrieval.semantic_fallback_used = True
            retrieval.similarity_score = sem_score
            retrieval.confidence_score = sem_score
            retrieval.retrieved_memory_items = [
                memory_row_to_trace_item(
                    mem2,
                    match_reason="semantic_fallback",
                    similarity_score=sem_score,
                )
            ]

    threshold = cfg.comparison_match_min_score

    if memory is None or confidence < threshold:
        retrieval.blocked_reason = retrieval.blocked_reason or "past_event_not_found"
        if semantic_used and sem_score is not None:
            retrieval.similarity_score = sem_score
        return PastEventResolution(
            is_past_event_query=True,
            found=False,
            intent=intent,
            reference_label=intent.reference_label,
            confidence=confidence,
            missing_message=_not_found_message(intent),
            chat_actions=_not_found_actions(intent),
            llm_allowed=False,
            retrieval=retrieval,
        )

    label = memory.value.strip().split("\n")[0][:120]
    if memory.event_date:
        label = f"{label} ({memory.event_date.isoformat()})"

    header = "COMPARISON GROUNDING" if intent.kind == "compare" else "PAST EVENT GROUNDING"
    grounding = format_grounding_block(
        reference_label=intent.reference_label,
        memory=memory,
        header=header,
    )

    return PastEventResolution(
        is_past_event_query=True,
        found=True,
        intent=intent,
        reference_label=label,
        confidence=confidence,
        grounding_context=grounding,
        matched_memory_ids=[str(memory.id)],
        llm_allowed=True,
        retrieval=retrieval,
    )


def build_not_found_reply(resolution: PastEventResolution) -> str:
    return resolution.missing_message
