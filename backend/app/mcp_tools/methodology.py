"""
Search parsed badminton methodology Markdown (output/*.md) for Analyst / MCP.

Uses chunking + lexical scoring (no extra API). Optional embedding boost later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

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


def search_sports_methodology(
    query: str,
    *,
    top_k: int = 5,
    sources: list[str] | None = None,
) -> list[dict]:
    """
    Return ranked snippets from sports methodology books for RAG-style grounding.

    Each item: source, page, score, snippet (max ~600 chars).
    """
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
    results: list[dict] = []
    for score, ch in scored[:top_k]:
        snippet = ch.text.replace("\n", " ").strip()
        if len(snippet) > 600:
            snippet = snippet[:597] + "..."
        results.append(
            {
                "source": ch.source,
                "page": ch.page_hint,
                "score": round(score, 3),
                "snippet": snippet,
            }
        )
    return results


def format_methodology_context(hits: list[dict]) -> str:
    if not hits:
        return ""
    lines = ["## Sports methodology (from parsed books)"]
    for i, h in enumerate(hits, 1):
        page = f", p.{h['page']}" if h.get("page") else ""
        lines.append(
            f"{i}. **{h['source']}{page}** (score {h['score']}): {h['snippet']}"
        )
    return "\n".join(lines)
