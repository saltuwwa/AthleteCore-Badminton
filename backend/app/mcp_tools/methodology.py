"""
Search parsed badminton methodology Markdown (output/*.md) for Analyst / MCP.

Primary: Qdrant vector RAG (text-embedding-3-small).
Fallback: lexical scoring when Qdrant is down or empty.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = PROJECT_ROOT / "output"

_CHUNK_CACHE: list["MethodologyChunk"] | None = None


@dataclass
class MethodologyChunk:
    source: str
    text: str
    page_hint: str | None = None


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]{3,}", text.lower())
    return set(words)


def _load_chunks() -> list[MethodologyChunk]:
    global _CHUNK_CACHE
    if _CHUNK_CACHE is not None:
        return _CHUNK_CACHE

    chunks: list[MethodologyChunk] = []
    if not OUTPUT_DIR.is_dir():
        _CHUNK_CACHE = []
        return _CHUNK_CACHE

    for path in sorted(OUTPUT_DIR.glob("*.md")):
        raw = path.read_text(encoding="utf-8", errors="ignore")
        parts = re.split(r"\n---\n|(?=<!-- page \d+ -->)", raw)
        for part in parts:
            text = part.strip()
            if len(text) < 80:
                continue
            page_m = re.search(r"page (\d+)", text[:80])
            chunks.append(
                MethodologyChunk(
                    source=path.name,
                    text=text[:4000],
                    page_hint=page_m.group(1) if page_m else None,
                )
            )

    _CHUNK_CACHE = chunks
    return _CHUNK_CACHE


_last_retrieval_debug: dict | None = None


def get_methodology_retrieval_debug() -> dict | None:
    """Debug payload from the most recent search_sports_methodology call."""
    return _last_retrieval_debug


def _apply_relevance_filter(
    query: str,
    candidates: list[dict],
    *,
    top_k: int,
) -> list[dict]:
    from app.rag.relevance_filter import filter_methodology_hits

    global _last_retrieval_debug
    accepted, debug = filter_methodology_hits(query, candidates, top_k=top_k)
    _last_retrieval_debug = debug
    return accepted


def _search_lexical(
    query: str,
    *,
    top_k: int = 5,
    sources: list[str] | None = None,
) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []

    chunks = _load_chunks()
    if sources:
        allow = {s.lower() for s in sources}
        chunks = [c for c in chunks if c.source.lower() in allow]
    if not chunks:
        return []

    q_tokens = _tokenize(query)
    if not q_tokens:
        return []

    scored: list[tuple[float, MethodologyChunk]] = []
    for ch in chunks:
        t_tokens = _tokenize(ch.text)
        if not t_tokens:
            continue
        overlap = len(q_tokens & t_tokens) / max(len(q_tokens), 1)
        phrase_bonus = 0.0
        q_lower = query.lower()
        if len(q_lower) > 4 and q_lower in ch.text.lower():
            phrase_bonus = 0.35
        domain_bonus = 0.0
        for kw in ("footwork", "работа ног", "split step", "lunge", "serve", "подач", "clear", "drop"):
            if kw in query.lower() and kw in ch.text.lower():
                domain_bonus += 0.05
        score = overlap + phrase_bonus + min(domain_bonus, 0.2)
        if score > 0.08:
            scored.append((score, ch))

    scored.sort(key=lambda x: x[0], reverse=True)
    pool_k = max(top_k * 4, 12)
    results: list[dict] = []
    for score, ch in scored[:pool_k]:
        snippet = ch.text.replace("\n", " ").strip()
        if len(snippet) > 600:
            snippet = snippet[:597] + "..."
        results.append(
            {
                "source": ch.source,
                "page": ch.page_hint,
                "score": round(score, 3),
                "snippet": snippet,
                "snippet_full": ch.text,
                "retrieval": "lexical",
            }
        )
    return _apply_relevance_filter(query, results, top_k=top_k)


def search_sports_methodology(
    query: str,
    *,
    top_k: int = 5,
    sources: list[str] | None = None,
) -> list[dict]:
    """
    Return ranked snippets from sports methodology books for RAG-style grounding.

    Each item: source, page, score, snippet, retrieval (qdrant|lexical).
    Irrelevant / off-domain queries return [] (see get_methodology_retrieval_debug).
    """
    global _last_retrieval_debug
    query = (query or "").strip()
    if not query:
        _last_retrieval_debug = {"query": "", "rejection_reason": "empty_query"}
        return []

    from app.cache.methodology_cache import (
        cache_key as methodology_cache_key,
        get_cached_hits,
        set_cached_hits,
    )

    mkey = methodology_cache_key(query, top_k=top_k)
    cached_hits = get_cached_hits(mkey)
    if cached_hits is not None:
        return cached_hits

    if settings.methodology_use_qdrant:
        try:
            from app.rag.retrieve import qdrant_available, search_methodology_rag

            if qdrant_available():
                raw = search_methodology_rag(
                    query, top_k=max(top_k * 4, 12), sources=sources
                )
                if raw:
                    hits = _apply_relevance_filter(query, raw, top_k=top_k)
                    set_cached_hits(mkey, hits)
                    return hits
        except Exception:
            pass

    if settings.methodology_fallback_lexical:
        hits = _search_lexical(query, top_k=top_k, sources=sources)
        set_cached_hits(mkey, hits)
        return hits

    from app.rag.relevance_filter import assess_query_domain

    _last_retrieval_debug = {
        **assess_query_domain(query),
        "rejection_reason": "no_retrieval_backend",
        "accepted_hits_count": 0,
    }
    return []


def format_methodology_context(hits: list[dict]) -> str:
    if not hits:
        return ""
    mode = hits[0].get("retrieval", "unknown")
    lines = [f"## Sports methodology (from parsed books, {mode})"]
    for i, h in enumerate(hits, 1):
        page = f", p.{h['page']}" if h.get("page") else ""
        lines.append(
            f"{i}. **{h['source']}{page}** (score {h['score']}): {h['snippet']}"
        )
    return "\n".join(lines)
