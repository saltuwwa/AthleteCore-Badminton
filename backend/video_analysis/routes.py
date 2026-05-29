from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from video_analysis.analyze_pipeline import run_video_analyze
from video_analysis.debug_report import load_debug_bundle
from video_analysis.player_tracking import (
    aggregate_players,
    ensure_tracking,
    render_preview_frame,
)
from video_analysis.preprocessing import load_meta, save_upload, video_paths
from video_analysis.schemas import (
    AnalyzeVideoRequest,
    AnalyzeVideoResponse,
    DetectPlayersRequest,
    DetectPlayersResponse,
    DetectedPlayer,
    PlayerBBox,
    VideoDebugSummary,
    VideoUploadResponse,
)

router = APIRouter(prefix="/video", tags=["video-analysis"])


def _build_debug_summary(video_id: str, metrics_match) -> VideoDebugSummary | None:
    bundle = load_debug_bundle(video_id)
    if not bundle:
        return None
    timing = bundle.get("12_timing_report") or bundle.get("00_debug_index", {}).get("timing", {})
    seg = bundle.get("05_segment_filtering") or {}
    if metrics_match and getattr(metrics_match, "segment_filter", None):
        seg = metrics_match.segment_filter.model_dump(mode="json")
    players = bundle.get("03_detected_players") or {}
    tracking = bundle.get("04_tracking_summary") or {}
    return VideoDebugSummary(
        valid_gameplay_ratio=float(seg.get("valid_gameplay_ratio", 0)),
        players_found=len(players.get("players", [])),
        tracking_stability=float(tracking.get("tracking_consistency_score", 0)),
        gemini_sec=timing.get("gemini_feedback_sec"),
        total_sec=timing.get("total_sec"),
    )


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

    max_p = body.max_players
    if max_p is None:
        max_p = 2 if body.match_type == "singles" else 4
    players_raw = aggregate_players(
        tracking,
        max_players=max_p,
        match_type=body.match_type,
        video_id=video_id,
    )
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
    debug: bool = Query(False, description="Enable eval/debug artifact export"),
):
    """
    Metrics → LTM video_analysis → patterns → Qdrant RAG → Gemini (no raw video).
    Pass debug=true (query or body) to write backend/reports/video_debug/{video_id}/.
    """
    body.debug = body.debug or debug
    load_meta(body.video_id)

    target_resolution: dict | None = None
    if body.match_type == "singles" and len(body.target_track_ids) > 1:
        if not body.target_court_side:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Singles with multiple target_track_ids requires target_court_side "
                    "(near|far) to pick the athlete track"
                ),
            )
        try:
            tracking = await asyncio.to_thread(ensure_tracking, body.video_id)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        from video_analysis.target_resolution import resolve_singles_target_tracks

        target_resolution = resolve_singles_target_tracks(
            tracking,
            body.target_track_ids,
            target_court_side=body.target_court_side,
            target_label=body.target_label,
        )
        body.target_track_ids = target_resolution["target_track_ids"]

    if body.match_type == "singles" and len(body.target_track_ids) != 1:
        raise HTTPException(status_code=400, detail="Singles requires exactly one target_track_id")
    if body.match_type == "doubles" and len(body.target_track_ids) < 2:
        raise HTTPException(status_code=400, detail="Doubles requires at least two target_track_ids")
    if body.match_type == "mixed" and len(body.target_track_ids) < 1:
        raise HTTPException(status_code=400, detail="Mixed requires at least one target_track_id")

    try:
        response = await run_video_analyze(
            session, body, debug=body.debug, target_resolution=target_resolution
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    if body.debug:
        response.debug_summary = _build_debug_summary(body.video_id, response.metrics)
    return response


@router.get("/{video_id}/debug")
async def get_video_debug_report(video_id: str):
    """Load full debug bundle for eval UI (dev only)."""
    load_meta(video_id)
    bundle = load_debug_bundle(video_id)
    if not bundle:
        raise HTTPException(status_code=404, detail=f"No debug report for video {video_id}")
    return bundle
