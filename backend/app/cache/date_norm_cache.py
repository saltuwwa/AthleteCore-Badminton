from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

_date_cache: dict[str, dict[str, Any]] = {}


def cache_key(raw_text: str, reference_date: date, timezone: str) -> str:
    payload = {
        "text": raw_text.strip(),
        "reference": reference_date.isoformat(),
        "timezone": timezone,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def get_cached(key: str) -> dict[str, Any] | None:
    return _date_cache.get(key)


def set_cached(key: str, value: dict[str, Any]) -> None:
    _date_cache[key] = value
