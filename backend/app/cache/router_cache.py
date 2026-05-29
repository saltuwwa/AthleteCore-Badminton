from __future__ import annotations

import hashlib
import json
import re
from datetime import date

from app.cache.ttl_cache import TtlCache

ROUTER_PROMPT_VERSION = "semantic-router-v1"
ROUTER_CACHE_TTL_SECONDS = 600.0  # 10 minutes

_router_cache: TtlCache[dict] = TtlCache(
    ttl_seconds=ROUTER_CACHE_TTL_SECONDS, max_entries=128
)

_CONTEXTUAL_DEICTIC = (
    "это ",
    "эту ",
    "этот ",
    "тогда ",
    "после этого",
    "после того",
    "тот матч",
    "та трениров",
    "тот раз",
)


def message_blocks_router_cache(user_input: str) -> bool:
    t = (user_input or "").lower()
    return any(m in t for m in _CONTEXTUAL_DEICTIC)


def normalize_message(user_input: str) -> str:
    return re.sub(r"\s+", " ", (user_input or "").strip().lower())


def cache_key(
    user_input: str,
    *,
    reference: date,
    model: str,
    thread_id: str | None = None,
) -> str:
    payload = {
        "message": normalize_message(user_input),
        "reference": reference.isoformat(),
        "model": model,
        "prompt_version": ROUTER_PROMPT_VERSION,
        "thread_id": thread_id if message_blocks_router_cache(user_input) else None,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()


def get_cached_router(key: str) -> dict | None:
    return _router_cache.get(key)


def set_cached_router(key: str, decision_dict: dict) -> None:
    _router_cache.set(key, decision_dict)
