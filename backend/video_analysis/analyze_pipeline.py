"""
Orchestrated video analyze pipeline with optional debug artifact collection.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.video_memory_service import (
    VideoMemoryContext,
    build_video_memory_context,
    persist_video_analysis_memories,
)
from app.memory.video_payload import build_video_analysis_payload, payload_to_episode_row
from app.memory.video_patterns import findings_to_semantic_candidates
from app.memory.write_gate import MemoryWriteGate
from video_analysis.badminton_metrics import build_metrics_summary
from video_analysis.debug_enrichment import (
    build_detected_players_debug,
    build_sampled_frames_debug,
    build_tracking_summary,
)
from video_analysis.debug_report import VideoDebugReporter, redact_secrets
from video_analysis.feedback_generation import generate_coaching_feedback
from video_analysis.player_tracking import aggregate_players, ensure_tracking
from video_analysis.preprocessing import load_meta, video_paths
from video_analysis.schemas import (
    AnalyzeVideoRequest,
    AnalyzeVideoResponse,
    CoachingFeedback,
    VideoMemorySummary,
    VideoMetricsSummary,
)

_write_gate = MemoryWriteGate()


def _target_type(match_type: str, n_targets: int) -> str:
    if match_type == "singles" or n_targets == 1:
        return "athlete"
    return "team"


def _format_gemini_feedback_md(feedback: CoachingFeedback, raw: str) -> str:
    lines = [
        "# Gemini coaching feedback",
        "",
        "## Parsed fields",
        f"**Summary:** {feedback.short_summary}",
        "",
        "### Timeline",
    ]
    for t in feedback.key_timeline_moments:
        lines.append(f"- {t}")
    lines.extend(
        [
            "",
            "### Recommendations",
            *[f"- {r}" for r in feedback.coaching_recommendations],
            "",
            f"**Drill:** {feedback.drill_for_next_training}",
            "",
            "## Raw Gemini JSON",
            "```json",
            raw,
            "```",
        ]
    )
    return "\n".join(lines)


async def run_video_analyze(
    session: AsyncSession,
    body: AnalyzeVideoRequest,
    *,
    debug: bool = False,
    target_resolution: dict[str, Any] | None = None,
) -> AnalyzeVideoResponse:
    reporter = VideoDebugReporter(body.video_id, enabled=debug)
    meta: dict[str, Any] = {}
    tracking: dict[str, Any] = {}
    players_raw: list[dict[str, Any]] = []
    metrics: VideoMetricsSummary | None = None
    memory_ctx: VideoMemoryContext | None = None
    feedback: CoachingFeedback | None = None
    gemini_debug: dict[str, Any] = {}

    try:
        with reporter.step("metadata"):
            meta = load_meta(body.video_id)
            reporter.write(
                "01_video_metadata.json",
                {
                    "filename": meta.get("filename"),
                    "duration_sec": meta.get("duration_sec"),
                    "fps": meta.get("fps"),
                    "resolution": {
                        "width": meta.get("width"),
                        "height": meta.get("height"),
                    },
                    "match_type": body.match_type,
                    "upload_time": meta.get("upload_time") or datetime.now(UTC).isoformat(),
                    "video_id": body.video_id,
                    "user_id": body.user_id,
                },
            )

        with reporter.step("tracking"):
            tracking = await asyncio.to_thread(ensure_tracking, body.video_id)
            reporter.write("02_sampled_frames.json", build_sampled_frames_debug(tracking))

        with reporter.step("player_detection"):
            players_raw = aggregate_players(
                tracking,
                match_type=body.match_type,
                video_id=body.video_id,
            )
            paths = video_paths(body.video_id)
            detected = build_detected_players_debug(
                tracking, players_raw, video_path=paths.get("video")
            )
            reporter.write("03_detected_players.json", {"players": detected})
            reporter.write(
                "04_tracking_summary.json",
                build_tracking_summary(tracking, body.target_track_ids),
            )

        duration = float(meta.get("duration_sec") or 0)
        if duration <= 0 and tracking.get("frames"):
            duration = float(tracking["frames"][-1].get("timestamp_sec", 0))

        metrics_match_type = (
            "doubles"
            if body.match_type == "mixed" and len(body.target_track_ids) >= 2
            else ("singles" if body.match_type == "mixed" else body.match_type)
        )

        with reporter.step("metrics_extraction"):
            metrics = build_metrics_summary(
                video_id=body.video_id,
                match_type=metrics_match_type,  # type: ignore[arg-type]
                target_track_ids=body.target_track_ids,
                tracking=tracking,
                duration_sec=duration,
            )
            if body.match_type == "mixed":
                metrics.match_type = "mixed"
            if metrics.segment_filter:
                sf = metrics.segment_filter.model_dump(mode="json")
                reporter.write(
                    "05_segment_filtering.json",
                    {
                        **sf,
                        "ignored_reason_labels": sorted(
                            {s["reason"] for s in sf.get("ignored_segments", [])}
                        ),
                    },
                )

        reporter.write(
            "06_target_selection.json",
            {
                "match_type": body.match_type,
                "target_type": _target_type(body.match_type, len(body.target_track_ids)),
                "target_track_ids": body.target_track_ids,
                "target_label": body.target_label,
                "target_jersey_color": body.target_jersey_color,
                "target_court_side": body.target_court_side,
                "target_resolution": target_resolution,
            },
        )
        reporter.write("07_metrics.json", metrics.model_dump(mode="json"))

        pre_payload = build_video_analysis_payload(
            user_id=body.user_id,
            metrics=metrics,
            coaching=None,
            match_type=body.match_type,
        )

        with reporter.step("memory_retrieval"):
            memory_ctx = await build_video_memory_context(
                session,
                body.user_id,
                pre_payload,
                exclude_video_id=body.video_id,
            )
            episodic = payload_to_episode_row(
                build_video_analysis_payload(
                    user_id=body.user_id,
                    metrics=metrics,
                    coaching=None,
                    match_type=body.match_type,
                )
            )
            semantic_candidates = findings_to_semantic_candidates(
                memory_ctx.repeated_patterns,
                memory_ctx.improvement_patterns,
                memory_ctx.athlete_baseline,
            )
            gated = _write_gate.filter_candidates([episodic] + semantic_candidates)
            reporter.write(
                "08_memory_context.json",
                {
                    "retrieved_previous_video_analysis_count": len(memory_ctx.past_episodes),
                    "repeated_patterns": memory_ctx.repeated_patterns,
                    "improvements": memory_ctx.improvement_patterns,
                    "regressions": [],
                    "athlete_baseline": memory_ctx.athlete_baseline,
                    "will_save_to_memory": [c.get("key") for c in gated],
                    "will_not_save": [
                        "raw_video_bytes",
                        "full_opponent_track_metrics",
                        "non_target_player_pose_series",
                        "gemini_full_prompt_unredacted",
                        "debug_artifacts",
                    ],
                    "target_only_metrics": True,
                    "target_track_ids": body.target_track_ids,
                },
            )

        with reporter.step("gemini_feedback"):
            result = await asyncio.to_thread(
                generate_coaching_feedback,
                metrics,
                memory_ctx,
                return_debug=debug,
            )
            if debug and isinstance(result, tuple):
                feedback, gemini_debug = result
            else:
                feedback = result  # type: ignore[assignment]

        if debug and gemini_debug:
            reporter.write(
                "09_rag_context.json",
                {
                    "chunks": gemini_debug.get("rag_hits", []),
                    "sources": gemini_debug.get("methodology_sources", []),
                },
            )
            reporter.write(
                "10_gemini_input.json",
                redact_secrets(gemini_debug.get("gemini_input", {})),
            )
            reporter.write(
                "11_gemini_feedback.md",
                _format_gemini_feedback_md(
                    feedback,
                    gemini_debug.get("gemini_raw_response", ""),
                ),
            )
        elif debug:
            reporter.write("10_gemini_input.json", {"error": "Gemini debug not captured"})
            reporter.write("11_gemini_feedback.md", feedback.model_dump_json(indent=2))

        with reporter.step("memory_write"):
            memory_ctx = await persist_video_analysis_memories(
                session,
                user_id=body.user_id,
                metrics=metrics,
                coaching=feedback,
                match_type=body.match_type,
            )

        paths = video_paths(body.video_id)
        paths["metrics"].write_text(metrics.model_dump_json(indent=2), encoding="utf-8")

    finally:
        if debug:
            reporter.finalize()

    assert metrics is not None and feedback is not None and memory_ctx is not None

    mem_summary = VideoMemorySummary(
        past_video_count=len(memory_ctx.past_episodes),
        repeated_patterns=[str(p.get("description", "")) for p in memory_ctx.repeated_patterns],
        improvement_patterns=[str(p.get("description", "")) for p in memory_ctx.improvement_patterns],
        athlete_baseline=memory_ctx.athlete_baseline,
    )

    return AnalyzeVideoResponse(
        video_id=body.video_id,
        metrics=metrics,
        coaching_feedback=feedback,
        memory_summary=mem_summary,
        debug_report_id=body.video_id if debug else None,
        debug_available=debug,
    )
