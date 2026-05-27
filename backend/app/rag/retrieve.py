"""Vector RAG retrieval for methodology books (Qdrant + optional rerank)."""

from __future__ import annotations

import asyncio
from typing import Any

from app.config import Settings, settings
from app.memory.embeddings import embed_query, openai_client

from .qdrant_store import collection_point_count, make_client, search_vectors

_rr_model = None


def _get_cross_encoder(cfg: Settings):
    global _rr_model
    if cfg.disable_reranker:
        return None
    if _rr_model is None:
        from sentence_transformers import CrossEncoder

        _rr_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _rr_model


def _embed_query_sync(cfg: Settings, text: str) -> list[float]:
    client = openai_client(cfg)

    async def _run():
        return await embed_query(
            client,
            cfg.embedding_model,
            text,
            dimensions=cfg.embedding_dimensions,
        )

    return asyncio.run(_run())


def _rerank(query: str, candidates: list[dict], cfg: Settings, top_k: int) -> list[dict]:
    model = _get_cross_encoder(cfg)
    if model is None or len(candidates) <= 1:
        return candidates[:top_k]
    pairs = [(query, c["snippet_full"]) for c in candidates]
    scores = model.predict(pairs)
    for c, s in zip(candidates, scores, strict=True):
        c["score"] = round(float(s), 4)
        c["reranked"] = True
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:top_k]


def qdrant_available(cfg: Settings | None = None) -> bool:
    cfg = cfg or settings
    if not cfg.methodology_use_qdrant:
        return False
    try:
        client = make_client(cfg)
        return collection_point_count(client, cfg.qdrant_collection_methodology) > 0
    except Exception:
        return False


def search_methodology_rag(
    query: str,
    *,
    top_k: int = 5,
    sources: list[str] | None = None,
    cfg: Settings | None = None,
) -> list[dict]:
    """
    Semantic search in Qdrant sports_methodology.
    Returns same shape as lexical search: source, page, score, snippet.
    """
    cfg = cfg or settings
    query = (query or "").strip()
    if not query or not cfg.openai_api_key:
        return []

    client = make_client(cfg)
    coll = cfg.qdrant_collection_methodology
    if collection_point_count(client, coll) == 0:
        return []

    query_vector = _embed_query_sync(cfg, query)
    raw_hits = search_vectors(
        client,
        coll,
        query_vector,
        limit=top_k * 3 if not cfg.disable_reranker else top_k,
        score_threshold=cfg.methodology_min_score,
    )

    candidates: list[dict] = []
    allow = {s.lower() for s in sources} if sources else None

    for hit in raw_hits:
        pl: dict[str, Any] = hit.payload or {}
        source = pl.get("source") or ""
        if allow and source.lower() not in allow:
            continue
        text = (pl.get("text") or "").strip()
        if not text:
            continue
        snippet = text.replace("\n", " ").strip()
        candidates.append(
            {
                "source": source,
                "page": pl.get("page"),
                "score": round(float(hit.score), 4),
                "snippet": snippet[:600] + ("..." if len(snippet) > 600 else ""),
                "snippet_full": text,
                "retrieval": "qdrant",
            }
        )

    if cfg.disable_reranker:
        return candidates[:top_k]
    return _rerank(query, candidates, cfg, top_k)
