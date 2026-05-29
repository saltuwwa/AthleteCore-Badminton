from __future__ import annotations

import hashlib
import json
from typing import Any

_embedding_cache: dict[str, list[float]] = {}


def _key(model: str, text: str, dimensions: int | None) -> str:
    payload = json.dumps(
        {"model": model, "text": text, "dimensions": dimensions},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_cached_embedding(
    model: str, text: str, *, dimensions: int | None
) -> list[float] | None:
    return _embedding_cache.get(_key(model, text, dimensions))


def set_cached_embedding(
    model: str, text: str, *, dimensions: int | None, vector: list[float]
) -> None:
    _embedding_cache[_key(model, text, dimensions)] = vector
