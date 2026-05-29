"""Normalize sport event dates from natural language (RU/EN) for memory write.

All calendar math uses ``datetime.date`` + ``timedelta`` / ``zoneinfo`` — never manual
day-number string subtraction. Relative phrases (вчера, прошлая неделя) resolve against
``reference_local_date`` in the athlete timezone (default Asia/Almaty).
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone as dt_timezone
from typing import Any, Callable

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_MEMORY_TIMEZONE = "Asia/Almaty"

# Fixed UTC offsets when IANA DB unavailable (Windows without `tzdata` package).
_FIXED_OFFSET_HOURS: dict[str, int] = {
    "Asia/Almaty": 5,
    "Asia/Aqtau": 5,
    "Asia/Aqtobe": 5,
    "Europe/Moscow": 3,
}


def get_timezone(tz_name: str) -> ZoneInfo | dt_timezone:
    """
    Resolve athlete timezone for calendar math.

    On Windows, install ``tzdata`` (see requirements.txt). If IANA data is still
    missing, use a fixed offset for known zones so chat does not crash.
    """
    name = (tz_name or DEFAULT_MEMORY_TIMEZONE).strip()
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        try:
            import tzdata  # noqa: F401 — registers IANA DB for zoneinfo on Windows

            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ImportError):
            hours = _FIXED_OFFSET_HOURS.get(name)
            if hours is not None:
                return dt_timezone(timedelta(hours=hours))
            return dt_timezone.utc

# --- month lexicons ---------------------------------------------------------

_MONTH_RU: dict[str, int] = {
    "январ": 1,
    "феврал": 2,
    "март": 3,
    "апр": 4,
    "мая": 5,
    "май": 5,
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентяб": 9,
    "октяб": 10,
    "нояб": 11,
    "декаб": 12,
}

_MONTH_EN: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

_WEEKDAY_RU: dict[str, int] = {
    "понедельник": 0,
    "вторник": 1,
    "сред": 2,
    "среду": 2,
    "четверг": 3,
    "пятниц": 4,
    "суббот": 5,
    "воскресень": 6,
}

_WEEKDAY_EN: dict[str, int] = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


@dataclass(frozen=True, slots=True)
class DateResolutionResult:
    event_date: date | None
    event_date_end: date | None
    confidence: float
    date_resolution_reason: str
    needs_clarification: bool = False
    clarification_message: str | None = None

    @property
    def resolved(self) -> bool:
        return self.event_date is not None and not self.needs_clarification

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_date": self.event_date.isoformat() if self.event_date else None,
            "event_date_end": self.event_date_end.isoformat() if self.event_date_end else None,
            "date_confidence": self.confidence,
            "date_normalization_reason": self.date_resolution_reason,
            "needs_clarification": self.needs_clarification,
            "clarification_message": self.clarification_message,
        }


def resolve_memory_timezone(
    *,
    profile_timezone: str | None = None,
    app_timezone: str | None = None,
) -> str:
    """Athlete profile TZ when set, else app default (Asia/Almaty)."""
    candidate = (profile_timezone or app_timezone or DEFAULT_MEMORY_TIMEZONE).strip()
    get_timezone(candidate)
    return candidate


def _empty(reason: str = "no_date_detected") -> DateResolutionResult:
    return DateResolutionResult(None, None, 0.0, reason)


def _resolved(
    start: date,
    end: date | None,
    confidence: float,
    reason: str,
) -> DateResolutionResult:
    return DateResolutionResult(start, end or start, confidence, reason)


def _clarification(
    reason: str,
    message: str,
) -> DateResolutionResult:
    return DateResolutionResult(
        None,
        None,
        0.0,
        reason,
        needs_clarification=True,
        clarification_message=message,
    )


def _month_name_ru(month: int) -> str:
    names = (
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
    if 1 <= month <= 12:
        return names[month - 1]
    return f"месяц {month}"


def _invalid_day_month_clarification(day: int, month: int, reference: date) -> DateResolutionResult:
    """31 апреля etc. — do not silently coerce; ask athlete."""
    month_label = _month_name_ru(month)
    year = pick_year_for_day_month(min(day, 28), month, reference)
    last_day = calendar.monthrange(year, month)[1]
    suggestions: list[str] = []
    if day > last_day:
        suggestions.append(f"{last_day} {month_label}")
    if month < 12:
        next_month = month + 1
        suggestions.append(f"1 {_month_name_ru(next_month)}")
    else:
        suggestions.append("1 января")
    if len(suggestions) == 1:
        hint = suggestions[0]
    else:
        hint = f"{suggestions[0]} или {suggestions[1]}"
    message = (
        f"{day} {month_label} не существует. "
        f"Ты имела в виду {hint}?"
    )
    return _clarification("invalid_calendar_date", message)


def parse_iso_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    s = str(value).strip()[:10]
    if not s:
        return None
    try:
        parts = s.split("-")
        if len(parts) == 3:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, TypeError):
        return None
    return None


def month_from_token(token: str) -> int | None:
    """RU month token (legacy export for match_comparison)."""
    return _month_num_from_token(token, _MONTH_RU)


def _month_num_from_token(token: str, table: dict[str, int]) -> int | None:
    t = token.lower().strip()
    for prefix, num in table.items():
        if t == prefix or t.startswith(prefix):
            return num
    if t.isdigit():
        n = int(t)
        if 1 <= n <= 12:
            return n
    return None


def reference_local_date(
    *,
    reference_datetime: datetime | date | None = None,
    turn_timestamp: datetime | date | None = None,
    timezone: str = DEFAULT_MEMORY_TIMEZONE,
) -> date:
    """Reference calendar date in athlete timezone."""
    ref = reference_datetime if reference_datetime is not None else turn_timestamp
    tz = get_timezone(timezone)
    if ref is None:
        return datetime.now(tz).date()
    if isinstance(ref, date) and not isinstance(ref, datetime):
        return ref
    if isinstance(ref, datetime):
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=tz)
        return ref.astimezone(tz).date()
    return date.today()


def pick_year_for_day_month(day: int, month: int, reference: date) -> int:
    """If day/month without year lands in the future, use previous year."""
    try:
        candidate = date(reference.year, month, day)
    except ValueError:
        return reference.year
    if candidate > reference:
        return reference.year - 1
    return reference.year


def _last_weekday_on_or_before(weekday: int, reference: date, *, force_previous: bool) -> date:
    """Most recent `weekday` (0=Mon) on or before reference; optional skip today."""
    delta = (reference.weekday() - weekday) % 7
    if delta == 0 and force_previous:
        delta = 7
    return reference - timedelta(days=delta)


def _week_range_monday_sunday(containing: date) -> tuple[date, date]:
    start = containing - timedelta(days=containing.weekday())
    return start, start + timedelta(days=6)


def _single_day_offset(days: int) -> Callable[[date], tuple[date, date]]:
    def fn(reference: date) -> tuple[date, date]:
        d = reference - timedelta(days=days)
        return d, d

    return fn


# --- resolvers (ordered strategies) -------------------------------------------

def _resolve_iso_fields(
    event_date_iso: Any,
    event_date_end_iso: Any,
) -> DateResolutionResult | None:
    start = parse_iso_date(event_date_iso)
    if not start:
        return None
    end = parse_iso_date(event_date_end_iso) or start
    return _resolved(start, end, 0.98, "extractor_iso_date")


def _resolve_iso_in_text(text: str) -> DateResolutionResult | None:
    iso = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    if iso:
        d = parse_iso_date(iso.group(1))
        if d:
            return _resolved(d, d, 0.97, "iso_in_text")
    dmy = re.search(r"\b(\d{1,2})[./](\d{1,2})[./](20\d{2})\b", text)
    if dmy:
        d, m, y = int(dmy.group(1)), int(dmy.group(2)), int(dmy.group(3))
        try:
            return _resolved(date(y, m, d), None, 0.96, "dmy_with_year")
        except ValueError:
            pass
    return None


def _resolve_relative(text: str, reference: date) -> DateResolutionResult | None:
    rules: list[tuple[str, Callable[[date], tuple[date, date]], float, str]] = [
        (
            r"\b(позавчера|two\s+days\s+ago|2\s+days\s+ago)\b",
            _single_day_offset(2),
            0.96,
            "relative_two_days_ago",
        ),
        (
            r"\b(вчера(?:шн\w*)?|yesterday)\b",
            _single_day_offset(1),
            0.97,
            "relative_yesterday",
        ),
        (
            r"\b(сегодня|today)\b",
            lambda r: (r, r),
            0.95,
            "relative_today",
        ),
        (
            r"\b(на прошлой неделе|прошлой неделе|last\s+week)\b",
            lambda r: _week_range_monday_sunday(r - timedelta(days=r.weekday() + 7)),
            0.9,
            "relative_last_week",
        ),
        (
            r"\b(на этой неделе|этой неделе|this\s+week)\b",
            lambda r: (r - timedelta(days=r.weekday()), r),
            0.85,
            "relative_this_week",
        ),
    ]
    for pattern, fn, conf, reason in rules:
        if re.search(pattern, text, re.IGNORECASE):
            start, end = fn(reference)
            return _resolved(start, end, conf, reason)
    return None


def _resolve_day_month(
    text: str,
    reference: date,
    *,
    lang: str,
) -> DateResolutionResult | None:
    table = _MONTH_RU if lang == "ru" else _MONTH_EN
    month_alt = "|".join(re.escape(k) for k in sorted(table.keys(), key=len, reverse=True))

    # 15 апреля / 10го апреля / 15 апр / April 15 / May 29
    patterns = [
        (
            rf"\b(\d{{1,2}})(?:-?го|-?е)?\s*(?:\.|/|-)?\s*({month_alt})(?:\w*)?\b",
            "day_month",
        ),
        (
            rf"\b(\d{{1,2}})\s*(?:\.|/|-)?\s*({month_alt})(?:\w*)?\b",
            "day_month",
        ),
        (
            rf"\b({month_alt})(?:\w*)?\s+(\d{{1,2}})\b",
            "month_day",
        ),
    ]
    for pat, order in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if not m:
            continue
        if order == "day_month":
            day, month_tok = int(m.group(1)), m.group(2)
        else:
            month_tok, day = m.group(1), int(m.group(2))
        month = _month_num_from_token(month_tok, table)
        if not month:
            continue
        year = pick_year_for_day_month(day, month, reference)
        try:
            d = date(year, month, day)
            return _resolved(d, d, 0.92, f"absolute_{lang}_{order}")
        except ValueError:
            return _invalid_day_month_clarification(day, month, reference)
    return None


def _resolve_weekday(text: str, reference: date) -> DateResolutionResult | None:
    force_prev = bool(
        re.search(
            r"\b(прошл|last)\s+(понедельник|вторник|сред|четверг|пятниц|суббот|воскресень|monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            text,
            re.IGNORECASE,
        )
    )
    for token, wd in _WEEKDAY_RU.items():
        if re.search(rf"\b(в\s+)?{token}", text, re.IGNORECASE):
            d = _last_weekday_on_or_before(wd, reference, force_previous=force_prev)
            return _resolved(d, d, 0.86, f"weekday_ru:{token}")
    for token, wd in _WEEKDAY_EN.items():
        if re.search(rf"\b(on\s+)?{token}\b", text, re.IGNORECASE):
            d = _last_weekday_on_or_before(wd, reference, force_previous=force_prev)
            return _resolved(d, d, 0.86, f"weekday_en:{token}")
    return None


def _date_result_from_cache(d: dict[str, Any]) -> DateResolutionResult:
    ed = d.get("event_date")
    ed_end = d.get("event_date_end")
    return DateResolutionResult(
        event_date=date.fromisoformat(ed) if ed else None,
        event_date_end=date.fromisoformat(ed_end) if ed_end else None,
        confidence=float(d.get("date_confidence", 0) or 0),
        date_resolution_reason=str(d.get("date_normalization_reason") or "cache"),
        needs_clarification=bool(d.get("needs_clarification")),
        clarification_message=d.get("clarification_message"),
    )


def normalize_memory_event_dates(
    raw_user_text: str,
    *,
    reference_datetime: datetime | date | None = None,
    turn_timestamp: datetime | date | None = None,
    timezone: str = DEFAULT_MEMORY_TIMEZONE,
    summary_text: str = "",
    event_date_iso: Any = None,
    event_date_end_iso: Any = None,
    event_date_phrase: str | None = None,
) -> DateResolutionResult:
    """
    Resolve when a sport event happened from user text + reference clock.

    Priority:
    1. Extractor ISO fields
    2. ISO / DMY in text
    3. Relative phrases (RU/EN)
    4. Absolute day+month (RU then EN)
    5. Weekday names (last occurrence on or before reference)
    """
    reference = reference_local_date(
        reference_datetime=reference_datetime,
        turn_timestamp=turn_timestamp,
        timezone=timezone,
    )
    blob = "\n".join(
        x for x in (raw_user_text, summary_text, event_date_phrase or "") if x
    ).strip()
    if not blob:
        return _empty("empty_text")

    from app.cache.date_norm_cache import cache_key as date_norm_key
    from app.cache.date_norm_cache import get_cached as get_date_norm_cached
    from app.cache.date_norm_cache import set_cached as set_date_norm_cached

    norm_key = date_norm_key(blob, reference, timezone)
    cached = get_date_norm_cached(norm_key)
    if cached is not None:
        return _date_result_from_cache(cached)

    for resolver in (
        lambda: _resolve_iso_fields(event_date_iso, event_date_end_iso),
        lambda: _resolve_iso_in_text(blob),
        lambda: _resolve_relative(blob.lower(), reference),
        lambda: _resolve_day_month(blob, reference, lang="ru"),
        lambda: _resolve_day_month(blob, reference, lang="en"),
        lambda: _resolve_weekday(blob, reference),
    ):
        hit = resolver()
        if hit:
            set_date_norm_cached(norm_key, hit.to_dict())
            return hit

    empty = _empty("no_matching_date_pattern")
    set_date_norm_cached(norm_key, empty.to_dict())
    return empty


def apply_calendar_to_semantic_fields(
    user_input: str,
    *,
    reference_datetime: datetime | date | None = None,
    timezone: str = DEFAULT_MEMORY_TIMEZONE,
    llm_event_date: str | None = None,
    llm_date_confidence: float = 0.0,
) -> DateResolutionResult:
    """
    Backend calendar resolution for semantic router / guard.

    LLM may flag that a relative date was mentioned; this function computes ISO dates.
    """
    if llm_event_date:
        iso = parse_iso_date(llm_event_date)
        if iso:
            return _resolved(iso, iso, max(llm_date_confidence, 0.85), "semantic_router_iso_hint")

    return normalize_memory_event_dates(
        user_input,
        reference_datetime=reference_datetime,
        timezone=timezone,
    )


# --- backward-compatible helpers --------------------------------------------

def normalize_relative_event_dates(
    text: str,
    reference: date,
) -> tuple[date | None, date | None]:
    """Legacy API used by past_event_guard."""
    result = normalize_memory_event_dates(
        text,
        reference_datetime=reference,
        timezone=DEFAULT_MEMORY_TIMEZONE,
    )
    return result.event_date, result.event_date_end


def parse_absolute_date_in_text(text: str, reference: date) -> date | None:
    """Calendar date in text (ISO or day+month), excluding relative-only phrases."""
    result = normalize_memory_event_dates(text, reference_datetime=reference)
    if not result.resolved:
        return None
    if result.date_resolution_reason.startswith("relative_"):
        return None
    return result.event_date


def resolve_event_dates(
    *,
    raw_user_text: str,
    summary_text: str,
    reference: date,
    event_date_iso: Any = None,
    event_date_end_iso: Any = None,
    event_date_phrase: str | None = None,
    timezone: str = DEFAULT_MEMORY_TIMEZONE,
) -> tuple[date | None, date | None]:
    """Legacy tuple API for write_enrichment."""
    result = normalize_memory_event_dates(
        raw_user_text,
        reference_datetime=reference,
        timezone=timezone,
        summary_text=summary_text,
        event_date_iso=event_date_iso,
        event_date_end_iso=event_date_end_iso,
        event_date_phrase=event_date_phrase,
    )
    return result.event_date, result.event_date_end
