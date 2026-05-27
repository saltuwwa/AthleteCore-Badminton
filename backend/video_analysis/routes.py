from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.memory.video_memory_service import (
    build_video_memory_context,
    persist_video_analysis_memories,
)
from app.memory.video_payload import build_video_analysis_payload
from app.video_analysis.segment_filter import filter_gameplay_segments
from video_analysis.badminton_metrics import build_metrics_summary
from video_analysis.feedback_generation import generate_coaching_feedback
from video_analysis.player_tracking import (
    aggregate_players,
    ensure_tracking,
    render_preview_frame,
)
from video_analysis.preprocessing import load_meta, save_upload, video_paths
from video_analysis.schemas import (
    AnalyzeVideoRequest,
    AnalyzeVideoResponse,
    VideoMemorySummary,
    DetectPlayersRequest,
    DetectPlayersResponse,
    DetectedPlayer,
    PlayerBBox,
    VideoUploadResponse,
)

router = APIRouter(prefix="/video", tags=["video-analysis"])


@router.post("/upload", response_model=VideoUploadResponse)
async def upload_video(file: UploadFile = File(...)):
    """Store match/training video locally for pose analysis (video never sent to LLM)."""
    meta = await save_upload(file)
    return VideoUploadResponse(
        video_id=meta["video_id"],
        filename=meta["filename"],
        duration_sec=meta.get("duration_sec"),
        fps=meta.get("fps"),
        frame_count=meta.get("frame_count"),
        width=meta.get("width"),
        height=meta.get("height"),
    )


@router.post("/detect-players", response_model=DetectPlayersResponse)
async def detect_players(body: DetectPlayersRequest):
    """
    Run YOLO pose + tracking, return 2–4 player candidates with preview frame.
    """
    video_id = body.video_id
    load_meta(video_id)
    paths = video_paths(video_id)

    try:
        tracking = await asyncio.to_thread(ensure_tracking, video_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    players_raw = aggregate_players(tracking, max_players=body.max_players)
    if len(players_raw) < 2:
        raise HTTPException(
            status_code=422,
            detail="Fewer than 2 players detected. Try a clearer side-view clip.",
        )

    players = [
        DetectedPlayer(
            track_id=p["track_id"],
            label=p["label"],
            bbox=PlayerBBox(**p["bbox"]),
            confidence=p["confidence"],
            frame_index=p["frame_index"],
            sample_count=p["sample_count"],
        )
        for p in players_raw
    ]

    preview_idx = players[0].frame_index
    try:
        preview_b64, preview_idx = await asyncio.to_thread(
            render_preview_frame,
            paths["video"],
            tracking,
            players_raw,
            frame_index=preview_idx,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview render failed: {e}") from e

    return DetectPlayersResponse(
        video_id=video_id,
        preview_frame_base64=preview_b64,
        preview_frame_index=preview_idx,
        players=players,
        tracking_available=True,
    )


@router.post("/analyze", response_model=AnalyzeVideoResponse)
async def analyze_video(
    body: AnalyzeVideoRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Metrics → LTM video_analysis → patterns → Qdrant RAG → Gemini (no raw video).
    """
    meta = load_meta(body.video_id)
    if body.match_type == "singles" and len(body.target_track_ids) != 1:
        raise HTTPException(status_code=400, detail="Singles requires exactly one target_track_id")
    if body.match_type == "doubles" and len(body.target_track_ids) < 2:
        raise HTTPException(status_code=400, detail="Doubles requires at least two target_track_ids")
    if body.match_type == "mixed" and len(body.target_track_ids) < 1:
        raise HTTPException(status_code=400, detail="Mixed requires at least one target_track_id")

    try:
        tracking = await asyncio.to_thread(ensure_tracking, body.video_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    # Gameplay segment filtering:
    # Only metrics computed from valid gameplay frames (replays, coach shots, pauses excluded).
    seg = filter_gameplay_segments(
        {
            **tracking,
            "match_type": body.match_type,
            "target_track_ids": body.target_track_ids,
        }
    )
    valid_key_set = set(seg.get("valid_timestamp_keys") or [])
    tracking = {
        **tracking,
        "frames": [fr for fr in (tracking.get("frames") or []) if f"{float(fr.get('timestamp_sec') or 0.0):.2f}" in valid_key_set],
    }

    duration = float(meta.get("duration_sec") or 0)
    if duration <= 0 and tracking.get("frames"):
        duration = float(tracking["frames"][-1].get("timestamp_sec", 0))

    metrics_match_type = "doubles" if body.match_type == "mixed" and len(body.target_track_ids) >= 2 else (
        "singles" if body.match_type == "mixed" else body.match_type
    )
    metrics = build_metrics_summary(
        video_id=body.video_id,
        match_type=metrics_match_type,  # type: ignore[arg-type]
        target_track_ids=body.target_track_ids,
        tracking=tracking,
        duration_sec=duration,
    )
    if body.match_type == "mixed":
        metrics.match_type = "mixed"

    # Expose compact segment filtering info to the frontend via raw_notes.
    ignored_replay_pause = any(
        s.get("reason") in ("replay_or_slow_motion", "pause")
        for s in (seg.get("ignored_segments") or [])
    )
    metrics.raw_notes.update(
        {
            "gameplay_segment_ratio": seg.get("valid_gameplay_ratio"),
            "segment_warning": seg.get("warning"),
            "excluded_replays_and_pauses": ignored_replay_pause,
        }
    )

    paths = video_paths(body.video_id)
    paths["metrics"].write_text(
        metrics.model_dump_json(indent=2),
        encoding="utf-8",
    )

    pre_payload = build_video_analysis_payload(
        user_id=body.user_id,
        metrics=metrics,
        coaching=None,
        match_type=body.match_type,
    )
    memory_ctx = await build_video_memory_context(
        session,
        body.user_id,
        pre_payload,
        exclude_video_id=body.video_id,
    )

    feedback = await asyncio.to_thread(generate_coaching_feedback, metrics, memory_ctx)

    memory_ctx = await persist_video_analysis_memories(
        session,
        user_id=body.user_id,
        metrics=metrics,
        coaching=feedback,
        match_type=body.match_type,
    )

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
    )
