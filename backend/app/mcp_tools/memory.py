"""LTM recall tool — same pipeline as /recall API."""

from __future__ import annotations

from app.database import AsyncSessionLocal
from app.memory.service import MemoryContextService


async def recall_athlete_memory(
    query: str,
    *,
    user_id: str = "aigerim",
    session_id: str = "main",
    max_tokens: int = 900,
) -> dict:
    """
    Hybrid memory recall for the athlete (semantic + episodic + procedural).

    Returns context text and citations for Analyst / Health Coach prompts.
    """
    query = (query or "").strip()
    if not query:
        return {"context": "", "citations": [], "note": "empty query"}

    async with AsyncSessionLocal() as session:
        svc = MemoryContextService()
        result = await svc.recall(
            session,
            query=query,
            session_id=session_id,
            user_id=user_id,
            max_tokens=max_tokens,
        )

    return {
        "context": result.context,
        "citations": [
            {
                "turn_id": c.turn_id,
                "score": c.score,
                "snippet": c.snippet,
                "memory_layer": c.memory_layer,
            }
            for c in result.citations
        ],
        "citation_count": len(result.citations),
    }
