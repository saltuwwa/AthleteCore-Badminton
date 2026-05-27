#!/usr/bin/env python3
"""
Ingest output/*.md coaching books into Qdrant collection sports_methodology.

Prerequisites:
  docker compose up -d qdrant
  OPENAI_API_KEY in backend/.env

Usage (from project root):
  python scripts/ingest_methodology_qdrant.py
  python scripts/ingest_methodology_qdrant.py --recreate
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / "backend" / ".env", override=False)

from app.config import Settings, load_settings
from app.memory.embeddings import embed_texts, openai_client
from app.rag.chunking import load_all_chunks
from app.rag.qdrant_store import (
    collection_point_count,
    ensure_collection,
    make_client,
    upsert_chunks,
)


async def ingest(*, recreate: bool) -> int:
    settings = load_settings()
    if not settings.openai_api_key:
        raise EnvironmentError("OPENAI_API_KEY required in backend/.env")

    chunks = load_all_chunks(
        max_tokens=settings.methodology_chunk_tokens,
        overlap_tokens=settings.methodology_chunk_overlap_tokens,
    )
    if not chunks:
        print("No chunks in output/*.md — parse PDFs first.", file=sys.stderr)
        return 1

    print(f"Chunks to embed: {len(chunks)}")
    client = make_client(settings)
    coll = settings.qdrant_collection_methodology
    ensure_collection(
        client,
        coll,
        vector_size=settings.embedding_dimensions,
        recreate=recreate,
    )

    oai = openai_client(settings)
    texts = [c.text for c in chunks]
    vectors: list[list[float]] = []
    batch = 64
    for i in range(0, len(texts), batch):
        batch_texts = texts[i : i + batch]
        batch_vecs = await embed_texts(
            oai,
            settings.embedding_model,
            batch_texts,
            dimensions=settings.embedding_dimensions,
        )
        vectors.extend(batch_vecs)
        print(f"  embedded {min(i + batch, len(texts))}/{len(texts)}")

    payloads = [
        {
            "source": c.source,
            "page": c.page,
            "chunk_index": c.chunk_index,
            "text": c.text,
            "chunk_id": c.chunk_id,
        }
        for c in chunks
    ]
    chunk_ids = [c.chunk_id for c in chunks]

    n = upsert_chunks(
        client,
        coll,
        vectors=vectors,
        payloads=payloads,
        chunk_ids=chunk_ids,
    )
    total = collection_point_count(client, coll)
    print(f"Upserted {n} points. Collection '{coll}' now has {total} vectors.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest methodology MD files into Qdrant.")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate the collection before ingest",
    )
    args = parser.parse_args()
    try:
        return asyncio.run(ingest(recreate=args.recreate))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
