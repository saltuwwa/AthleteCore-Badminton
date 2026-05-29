"""Calendar date normalization — real arithmetic, Asia/Almaty, invalid dates."""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.memory.date_normalizer import (
    DateResolutionResult,
    get_timezone,
    normalize_memory_event_dates,
    normalize_relative_event_dates,
    reference_local_date,
    resolve_event_dates,
    resolve_memory_timezone,
)
from zoneinfo import ZoneInfoNotFoundError

TZ = "Asia/Almaty"


def _ref(d: date) -> datetime:
    """Noon on reference day in Almaty (UTC+5)."""
    return datetime(d.year, d.month, d.day, 12, 0, tzinfo=timezone(timedelta(hours=5)))


def _norm(text: str, ref: date) -> DateResolutionResult:
    return normalize_memory_event_dates(
        text,
        reference_datetime=_ref(ref),
        timezone=TZ,
    )


# --- Test 1–4: вчера across month boundaries ---------------------------------


def test_yesterday_may_29():
    r = _norm("вчера была тренировка", date(2026, 5, 29))
    assert r.event_date == date(2026, 5, 28)
    assert r.needs_clarification is False


def test_yesterday_may_1():
    r = _norm("вчера была тренировка", date(2026, 5, 1))
    assert r.event_date == date(2026, 4, 30)


def test_yesterday_march_1_non_leap():
    r = _norm("вчера была тренировка", date(2026, 3, 1))
    assert r.event_date == date(2026, 2, 28)


def test_yesterday_march_1_leap_year():
    r = _norm("вчера была тренировка", date(2028, 3, 1))
    assert r.event_date == date(2028, 2, 29)


# --- Test 5–6: absolute day+month + year roll --------------------------------


def test_feb_8_go_typo():
    r = _norm("8го февраля была тренировка", date(2026, 5, 29))
    assert r.event_date == date(2026, 2, 8)


def test_december_20_previous_year():
    r = _norm("20 декабря была тренировка", date(2026, 1, 10))
    assert r.event_date == date(2025, 12, 20)


# --- Test 7: invalid calendar date --------------------------------------------


def test_april_31_needs_clarification():
    r = _norm("31 апреля была тренировка", date(2026, 5, 29))
    assert r.event_date is None
    assert r.needs_clarification is True
    assert r.clarification_message
    assert "31" in r.clarification_message
    assert "апрел" in r.clarification_message.lower()
    assert "не существует" in r.clarification_message.lower()


# --- Test 8: last week Mon–Sun ------------------------------------------------


def test_last_week_monday_sunday():
    r = _norm("на прошлой неделе была тренировка", date(2026, 5, 29))
    assert r.event_date == date(2026, 5, 18)
    assert r.event_date_end == date(2026, 5, 24)
    assert r.date_resolution_reason == "relative_last_week"


# --- structured export + timezone --------------------------------------------


def test_to_dict_shape():
    r = _norm("вчера была тренировка", date(2026, 5, 29))
    d = r.to_dict()
    assert d["event_date"] == "2026-05-28"
    assert d["date_confidence"] >= 0.9
    assert d["date_normalization_reason"] == "relative_yesterday"
    assert d["needs_clarification"] is False


def test_get_timezone_fallback_when_iana_db_missing(monkeypatch):
    """Windows without tzdata used to crash with ZoneInfoNotFoundError."""

    def _missing(_key: str):
        raise ZoneInfoNotFoundError("No time zone found with key Asia/Almaty")

    monkeypatch.setattr("app.memory.date_normalizer.ZoneInfo", _missing)
    tz = get_timezone("Asia/Almaty")
    from datetime import timezone as dt_timezone

    assert isinstance(tz, dt_timezone)
    ref = reference_local_date(
        reference_datetime=datetime(2026, 5, 29, 12, 0, tzinfo=tz),
        timezone="Asia/Almaty",
    )
    assert ref == date(2026, 5, 29)


def test_resolve_memory_timezone_profile_wins():
    assert (
        resolve_memory_timezone(
            profile_timezone="Europe/Moscow",
            app_timezone="Asia/Almaty",
        )
        == "Europe/Moscow"
    )


def test_reference_local_date_from_offset_datetime():
    ref_dt = datetime(2026, 5, 29, 10, 0, tzinfo=timezone(timedelta(hours=5)))
    assert reference_local_date(reference_datetime=ref_dt, timezone=TZ) == date(2026, 5, 29)


def test_april_15_ru_without_year():
    r = _norm("15 апреля играла матч", date(2026, 5, 29))
    assert r.event_date == date(2026, 4, 15)


def test_yesterday_en():
    r = _norm("Yesterday I had recovery session", date(2026, 5, 29))
    assert r.event_date == date(2026, 5, 28)


def test_legacy_resolve_event_dates():
    start, end = resolve_event_dates(
        raw_user_text="Вчера была силовая тренировка",
        summary_text="",
        reference=date(2026, 5, 29),
        timezone=TZ,
    )
    assert start == date(2026, 5, 28)


def test_legacy_normalize_relative():
    start, end = normalize_relative_event_dates("Вчера была тренировка", date(2026, 5, 29))
    assert start == date(2026, 5, 28)
    assert end == date(2026, 5, 28)
