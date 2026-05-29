from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from app.cache.ttl_cache import TtlCache
from app.mcp_tools.methodology import OUTPUT_DIR

_methodology_cache: TtlCache[list[dict]] = TtlCache(ttl_seconds=3600.0, max_entries=256)
_CORPUS_VERSION: str | None = None


def _corpus_version() -> str:
    global _CORPUS_VERSION
    if _CORPUS_VERSION is not None:
        return _CORPUS_VERSION
    if not OUTPUT_DIR.is_dir():
        _CORPUS_VERSION = "empty"
        return _CORPUS_VERSION
    parts: list[str] = []
    for path in sorted(OUTPUT_DIR.glob("*.md")):
        stat = path.stat()
        parts.append(f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
    _CORPUS_VERSION = hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
    return _CORPUS_VERSION


def _normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", (query or "").strip().lower())


def cache_key(query: str, *, top_k: int, sport: str = "badminton") -> str:
    payload = {
        "q": _normalize_query(query),
        "top_k": top_k,
        "sport": sport,
        "corpus": _corpus_version(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()


def get_cached_hits(key: str) -> list[dict] | None:
    return _methodology_cache.get(key)


def set_cached_hits(key: str, hits: list[dict]) -> None:
    _methodology_cache.set(key, hits)
