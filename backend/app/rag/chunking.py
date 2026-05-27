"""Chunk parsed methodology Markdown for vector ingest."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import tiktoken

PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = PROJECT_ROOT / "output"

_JUNK_LINE = re.compile(
    r"fliphtml5|flip pdf download|fliphtml5\.com|NO_CONTENT_HERE",
    re.I,
)


@dataclass
class MethodologyChunkDoc:
    source: str
    page: str | None
    chunk_index: int
    text: str

    @property
    def chunk_id(self) -> str:
        p = self.page or "0"
        return f"{self.source}::p{p}::c{self.chunk_index}"


def _encoding():
    return tiktoken.get_encoding("cl100k_base")


def _split_oversized(text: str, max_tokens: int, overlap: int) -> list[str]:
    enc = _encoding()
    tokens = enc.encode(text)
    if len(tokens) <= max_tokens:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        parts.append(enc.decode(tokens[start:end]))
        if end >= len(tokens):
            break
        start = max(0, end - overlap)
    return parts


def _clean_page_text(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if _JUNK_LINE.search(line):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def iter_chunks_from_markdown(
    md_path: Path,
    *,
    max_tokens: int = 900,
    overlap_tokens: int = 120,
    min_chars: int = 80,
) -> list[MethodologyChunkDoc]:
    raw = md_path.read_text(encoding="utf-8", errors="ignore")
    source = md_path.name
    parts = re.split(r"(?=<!-- page \d+ -->)", raw)
    docs: list[MethodologyChunkDoc] = []

    for part in parts:
        part = part.strip()
        if len(part) < min_chars:
            continue
        page_m = re.search(r"<!-- page (\d+) -->", part)
        page = page_m.group(1) if page_m else None
        body = _clean_page_text(re.sub(r"<!-- page \d+ -->\s*", "", part, count=1))
        if len(body) < min_chars:
            continue
        sub_chunks = _split_oversized(body, max_tokens, overlap_tokens)
        for idx, sub in enumerate(sub_chunks):
            if len(sub.strip()) < min_chars:
                continue
            docs.append(
                MethodologyChunkDoc(
                    source=source,
                    page=page,
                    chunk_index=idx,
                    text=sub.strip(),
                )
            )
    return docs


def load_all_chunks(
    output_dir: Path | None = None,
    *,
    max_tokens: int = 900,
    overlap_tokens: int = 120,
) -> list[MethodologyChunkDoc]:
    out = output_dir or OUTPUT_DIR
    if not out.is_dir():
        return []
    all_docs: list[MethodologyChunkDoc] = []
    for path in sorted(out.glob("*.md")):
        all_docs.extend(
            iter_chunks_from_markdown(
                path, max_tokens=max_tokens, overlap_tokens=overlap_tokens
            )
        )
    return all_docs
