from __future__ import annotations

import math

from .models import Memory


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def max_query_memory_similarity(query_emb: list[float], memories: list[Memory]) -> float:
    best = 0.0
    for m in memories:
        if not m.embedding:
            continue
        best = max(best, cosine_similarity(query_emb, m.embedding))
    return best


def gate_stable_rows(
    query_emb: list[float],
    stable_rows: list[Memory],
    min_cos: float,
) -> list[Memory]:
    if min_cos <= 0.0 or not stable_rows:
        return stable_rows
    if max_query_memory_similarity(query_emb, stable_rows) < min_cos:
        return []
    return stable_rows


def gate_ranked_memories(
    query_emb: list[float],
    ranked: list[tuple[Memory, float]],
    min_cos: float,
) -> list[tuple[Memory, float]]:
    if min_cos <= 0.0 or not ranked:
        return ranked
    mems = [m for m, _ in ranked]
    if max_query_memory_similarity(query_emb, mems) < min_cos:
        return []
    return ranked


def inject_high_risk_health(
    ranked: list[tuple[Memory, float]],
    all_scoped: list[Memory],
    limit: int,
) -> list[tuple[Memory, float]]:
    """AthleteCore rule: high-risk health memories always considered for recall."""
    from .models import RiskLevel

    seen = {m.id for m, _ in ranked}
    out = list(ranked)
    for m in all_scoped:
        if m.risk_level != RiskLevel.high or m.id in seen:
            continue
        out.append((m, 0.95))
        seen.add(m.id)
    out.sort(key=lambda x: x[1], reverse=True)
    return out[:limit]
