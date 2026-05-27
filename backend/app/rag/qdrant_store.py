"""Qdrant client helpers for sports_methodology collection."""

from __future__ import annotations

import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.config import Settings


def make_client(settings: Settings) -> QdrantClient:
    return QdrantClient(
        url=settings.qdrant_url,
        timeout=settings.qdrant_timeout_sec,
        check_compatibility=False,
    )


def collection_exists(client: QdrantClient, name: str) -> bool:
    try:
        names = {c.name for c in client.get_collections().collections}
        return name in names
    except Exception:
        return False


def ensure_collection(
    client: QdrantClient,
    name: str,
    *,
    vector_size: int,
    recreate: bool = False,
) -> None:
    if recreate and collection_exists(client, name):
        client.delete_collection(name)
    if collection_exists(client, name):
        return
    client.create_collection(
        collection_name=name,
        vectors_config=qm.VectorParams(size=vector_size, distance=qm.Distance.COSINE),
    )


def point_id_from_chunk_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def upsert_chunks(
    client: QdrantClient,
    collection: str,
    *,
    vectors: list[list[float]],
    payloads: list[dict[str, Any]],
    chunk_ids: list[str],
    batch_size: int = 64,
) -> int:
    total = 0
    for i in range(0, len(vectors), batch_size):
        batch_v = vectors[i : i + batch_size]
        batch_p = payloads[i : i + batch_size]
        batch_ids = chunk_ids[i : i + batch_size]
        points = [
            qm.PointStruct(
                id=point_id_from_chunk_id(cid),
                vector=vec,
                payload=pl,
            )
            for cid, vec, pl in zip(batch_ids, batch_v, batch_p, strict=True)
        ]
        client.upsert(collection_name=collection, points=points)
        total += len(points)
    return total


def search_vectors(
    client: QdrantClient,
    collection: str,
    query_vector: list[float],
    *,
    limit: int = 10,
    score_threshold: float | None = None,
) -> list[qm.ScoredPoint]:
    return client.search(
        collection_name=collection,
        query_vector=query_vector,
        limit=limit,
        score_threshold=score_threshold,
        with_payload=True,
    )


def collection_point_count(client: QdrantClient, collection: str) -> int:
    try:
        info = client.get_collection(collection)
        return int(info.points_count or 0)
    except Exception:
        return 0
