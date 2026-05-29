"""Simple TTL cache for dev/single-worker MVP."""

from __future__ import annotations

import time
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class TtlCache(Generic[T]):
    def __init__(self, ttl_seconds: float, *, max_entries: int = 512) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._data: dict[str, tuple[float, T]] = {}

    def get(self, key: str) -> T | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            self._data.pop(key, None)
            return None
        return value

    def set(self, key: str, value: T) -> None:
        if len(self._data) >= self._max:
            oldest = min(self._data.items(), key=lambda x: x[1][0])
            self._data.pop(oldest[0], None)
        self._data[key] = (time.monotonic() + self._ttl, value)
