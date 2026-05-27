from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.memory.embeddings import embed_texts, openai_client
from app.memory.models import Memory, Turn
from app.memory.supersession import apply_supersession_and_insert
from app.memory.video_patterns import (
    build_athlete_baseline,
    detect_improvements,
    detect_repeated_issues,
    findings_to_semantic_candidates,
)
from app.memory.video_payload import (
    build_video_analysis_payload,
    episode_from_memory_row,
    payload_to_episode_row,
)
from app.memory.write_gate import MemoryWriteGate
from video_analysis.schemas import CoachingFeedback, VideoMetricsSummary

VIDEO_HISTORY_LIMIT = 10
_video_write_gate = MemoryWriteGate()


@dataclass
class VideoMemoryContext:
    past_episodes: list[dict] = field(default_factory=list)
    repeated_patterns: list[dict] = field(default_factory=list)
    improvement_patterns: list[dict] = field(default_factory=list)
    athlete_baseline: dict | None = None

    def format_for_prompt(self) -> str:
        lines: list[str] = []
        if self.athlete_baseline:
            lines.append("## Athlete video baseline (semantic, approximate)")
            lines.append(str(self.athlete_baseline))
        if self.repeated_patterns:
            lines.append("## Repeated issues across recent videos")
            for p in self.repeated_patterns:
                lines.append(f"- {p.get('description', p)}")
        if self.improvement_patterns:
            lines.append("## Improvements across recent videos")
            for p in self.improvement_patterns:
                lines.append(f"- {p.get('description', p)}")
        if self.past_episodes:
            lines.append("## Recent video_analysis episodes (episodic)")
            for ep in self.past_episodes[-5:]:
                lines.append(
                    f"- {ep.get('timestamp', '')[:10]} "
                    f"{ep.get('match_type')} "
                    f"issues={ep.get('detected_issues')} "
                    f"drop={ep.get('speed_drop_percent')}"
                )
        return "\n".join(lines)


async def fetch_video_analysis_episodes(
    session: AsyncSession,
    user_id: str,
    *,
    limit: int = VIDEO_HISTORY_LIMIT,
    exclude_video_id: str | None = None,
) -> list[dict]:
    stmt = (
        select(Memory)
        .where(
            Memory.user_id == user_id,
            Memory.active.is_(True),
            Memory.event_type == "video_analysis",
        )
        .order_by(Memory.created_at.desc())
        .limit(limit + 5)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    episodes: list[dict] = []
    for row in rows:
        ep = episode_from_memory_row(row)
        if exclude_video_id and ep.get("source_video_id") == exclude_video_id:
            continue
        episodes.append(ep)
        if len(episodes) >= limit:
            break
    return episodes


async def build_video_memory_context(
    session: AsyncSession,
    user_id: str,
    current_payload: dict,
    *,
    exclude_video_id: str | None = None,
) -> VideoMemoryContext:
    past = await fetch_video_analysis_episodes(
        session, user_id, limit=VIDEO_HISTORY_LIMIT, exclude_video_id=exclude_video_id
    )
    all_for_patterns = past + [current_payload]
    repeated = detect_repeated_issues(all_for_patterns)
    improvements = detect_improvements(all_for_patterns)
    baseline = build_athlete_baseline(all_for_patterns)
    return VideoMemoryContext(
        past_episodes=past,
        repeated_patterns=repeated,
        improvement_patterns=improvements,
        athlete_baseline=baseline,
    )


async def _embed_candidates(candidates: list[dict]) -> list[list[float]]:
    if not candidates or not settings.openai_api_key:
        return [[] for _ in candidates]
    client = openai_client(settings)
    texts = [f"{c['key']}: {c['value']}" for c in candidates]
    return await embed_texts(
        client,
        settings.embedding_model,
        texts,
        dimensions=settings.embedding_dimensions,
    )


async def persist_video_analysis_memories(
    session: AsyncSession,
    *,
    user_id: str,
    metrics: VideoMetricsSummary,
    coaching: CoachingFeedback,
    session_id: str | None = None,
    match_type: str | None = None,
) -> VideoMemoryContext:
    """
    Cold path after video analyze:
    1) episodic video_analysis
    2) pattern detection on last N + current
    3) derived semantic memories (high confidence only)
    """
    sid = session_id or f"video:{user_id}"
    payload = build_video_analysis_payload(
        user_id=user_id,
        metrics=metrics,
        coaching=coaching,
        match_type=match_type,  # type: ignore[arg-type]
    )

    ctx = await build_video_memory_context(
        session, user_id, payload, exclude_video_id=metrics.video_id
    )

    turn = Turn(
        session_id=sid,
        user_id=user_id,
        messages=[
            {
                "role": "system",
                "content": f"video_analysis:{metrics.video_id}",
            }
        ],
        turn_timestamp=datetime.now(UTC),
        metadata_={"source": "video_analysis", "video_id": metrics.video_id},
    )
    session.add(turn)
    await session.flush()

    episodic = payload_to_episode_row(payload)
    semantic_candidates = findings_to_semantic_candidates(
        ctx.repeated_patterns,
        ctx.improvement_patterns,
        ctx.athlete_baseline,
    )

    all_candidates = [episodic] + semantic_candidates
    gated = _video_write_gate.filter_candidates(all_candidates)
    embeddings = await _embed_candidates(gated)

    if gated:
        await apply_supersession_and_insert(
            session,
            user_id=user_id,
            source_session=sid,
            source_turn_id=turn.id,
            candidates=gated,
            embeddings=embeddings,
        )

    await session.commit()
    return ctx
