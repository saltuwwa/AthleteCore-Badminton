"""Facade for LangGraph nodes and HTTP recall."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, settings
from app.schemas import Citation, RecallOut

from .context_assembly import (
    build_recall_context,
    fetch_procedural_memories,
    fetch_stable_profile_memories,
)
from .embeddings import embed_query, openai_client
from .recall_gating import gate_ranked_memories, gate_stable_rows
from .retrieval import fetch_high_risk_memories, hybrid_search, recent_turn_snippets


@dataclass(slots=True)
class AgentMemoryContext:
    context: str
    citations: list[Citation]


class MemoryContextService:
    def __init__(self, app_settings: Settings | None = None) -> None:
        self.settings = app_settings or settings

    async def recall(
        self,
        session: AsyncSession,
        *,
        query: str,
        session_id: str,
        user_id: str | None,
        max_tokens: int = 1024,
    ) -> AgentMemoryContext:
        if not self.settings.openai_api_key:
            return AgentMemoryContext(context="", citations=[])

        client = openai_client(self.settings)
        q_emb = await embed_query(
            client,
            self.settings.embedding_model,
            query,
            dimensions=self.settings.embedding_dimensions,
        )

        ranked = await hybrid_search(
            session,
            self.settings,
            query=query,
            user_id=user_id,
            session_id=session_id,
            limit=18,
            query_embedding=q_emb,
        )
        ranked = gate_ranked_memories(q_emb, ranked, self.settings.recall_ranked_min_cos)

        high_risk = await fetch_high_risk_memories(
            session, user_id=user_id, session_id=session_id
        )
        seen = {m.id for m, _ in ranked}
        for m in high_risk:
            if m.id not in seen:
                ranked.append((m, 0.95))

        stable = await fetch_stable_profile_memories(
            session, user_id=user_id, session_id=session_id
        )
        stable = gate_stable_rows(q_emb, stable, self.settings.recall_stable_min_cos)

        procedural = await fetch_procedural_memories(
            session, user_id=user_id, session_id=session_id
        )

        recent = await recent_turn_snippets(
            session, session_id=session_id, user_id=user_id
        )
        recent_lines = [(label, blob[:1200]) for label, blob in recent]

        ctx, cites = build_recall_context(
            max_tokens=max_tokens,
            stable_rows=stable,
            procedural_rows=procedural,
            ranked_memories=ranked,
            recent_lines=recent_lines,
        )
        citations = [
            Citation(turn_id=a, score=s, snippet=sn[:500], memory_layer=layer)
            for (a, sn, s, layer) in cites
        ]
        return AgentMemoryContext(context=ctx, citations=citations)

    async def recall_http(
        self,
        session: AsyncSession,
        *,
        query: str,
        session_id: str,
        user_id: str | None,
        max_tokens: int,
    ) -> RecallOut:
        result = await self.recall(
            session,
            query=query,
            session_id=session_id,
            user_id=user_id,
            max_tokens=max_tokens,
        )
        return RecallOut(context=result.context, citations=result.citations)
