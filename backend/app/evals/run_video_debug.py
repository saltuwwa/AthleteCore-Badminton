"""
Local video analysis debug runner.

Examples (PowerShell):
  python -m app.evals.run_video_debug --video "C:\\path\\match.mp4" --match-type singles --detect-only
  python -m app.evals.run_video_debug --video "C:\\path\\match.mp4" --user-id aigerim --match-type singles --target-track-ids 1 --debug
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


async def _run_detect_only(args: argparse.Namespace) -> int:
    from video_analysis.debug_report import debug_report_dir, save_preview_image
    from video_analysis.player_tracking import (
        aggregate_players,
        ensure_tracking,
        render_preview_candidates_frame,
        render_preview_frame,
    )
    from video_analysis.preprocessing import register_video_from_path, video_paths

    meta = register_video_from_path(Path(args.video), filename=Path(args.video).name)
    video_id = meta["video_id"]
    dur = meta.get("duration_sec")
    print(f"video_id={video_id}")
    if dur:
        print(
            f"duration~{float(dur):.0f}s - YOLO tracking on CPU can take several minutes, progress below..."
        )
    else:
        print("Running YOLO pose + tracking (CPU may take several minutes, progress below)…")

  # Faster stride for detect-only preview (full analyze uses default stride=2 from cache)
    tracking = ensure_tracking(video_id, vid_stride=4, show_progress=True)
    exclude_ids = [int(x) for x in args.exclude_track_ids.split(",") if x.strip()] if args.exclude_track_ids else []
    players = aggregate_players(
        tracking,
        match_type=args.match_type,
        video_id=video_id,
        exclude_track_ids=exclude_ids,
    )
    paths = video_paths(video_id)

    preview_b64, _ = render_preview_frame(
        paths["video"], tracking, players, frame_index=players[0]["frame_index"] if players else 0
    )
    if preview_b64.startswith("data:image/jpeg;base64,"):
        raw = base64.b64decode(preview_b64.split(",", 1)[1])
        rel = save_preview_image(video_id, raw, "preview_players.jpg")
        print(f"preview saved: {rel}")

    out_dir = debug_report_dir(video_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    candidates_path = out_dir / "player_candidates.json"
    eval_path = out_dir / "player_selection_eval.json"
    candidates_path.write_text(
        json.dumps({"video_id": video_id, "players": players}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"players: {candidates_path}")
    if eval_path.is_file():
        print(f"selection eval: {eval_path}")
        ev = json.loads(eval_path.read_text(encoding="utf-8"))
        try:
            cand_b64, _ = render_preview_candidates_frame(
                paths["video"],
                tracking,
                ev,
                frame_index=players[0]["frame_index"] if players else None,
            )
            raw = base64.b64decode(cand_b64.split(",", 1)[1])
            rel = save_preview_image(video_id, raw, "preview_candidates.jpg")
            print(f"preview candidates: {rel}")
        except Exception as e:
            print(f"WARNING: failed to render preview_candidates.jpg: {e}", file=sys.stderr)
    for p in players:
        low = " [low_stability]" if p.get("low_stability") else ""
        print(
            f"  track_id={p['track_id']} label={p['label']} samples={p['sample_count']}"
            f" court_validity={p.get('court_validity_score')}{low}"
        )
    if eval_path.is_file():
        ev = json.loads(eval_path.read_text(encoding="utf-8"))
        for w in ev.get("selection_warnings", []):
            print(w)
    print(
        "\nManual override for full analyze:\n"
        f'  --target-track-ids {",".join(str(p["track_id"]) for p in players)}'
    )
    return 0


async def _run_analyze(args: argparse.Namespace) -> int:
    from app.database import AsyncSessionLocal, init_db
    from video_analysis.analyze_pipeline import run_video_analyze
    from video_analysis.debug_report import debug_report_dir
    from video_analysis.player_tracking import ensure_tracking
    from video_analysis.preprocessing import register_video_from_path
    from video_analysis.schemas import AnalyzeVideoRequest
    from video_analysis.target_resolution import (
        format_target_resolution_summary,
        resolve_singles_target_tracks,
    )

    meta = register_video_from_path(Path(args.video), filename=Path(args.video).name)
    video_id = meta["video_id"]
    print(f"video_id={video_id}")

    track_ids = [int(x) for x in args.target_track_ids.split(",") if x.strip()] if args.target_track_ids else []
    exclude_ids = [int(x) for x in args.exclude_track_ids.split(",") if x.strip()] if args.exclude_track_ids else []
    if not track_ids and not args.detect_only:
        print("ERROR: provide --target-track-ids or run --detect-only first", file=sys.stderr)
        return 2

    analyze_target_ids = track_ids
    resolved = None
    if args.match_type == "singles" and len(track_ids) >= 1:
        tracking = ensure_tracking(video_id, show_progress=False)
        resolved = resolve_singles_target_tracks(
            tracking,
            track_ids,
            target_court_side=args.target_court_side,
            target_label=args.target_label,
            exclude_track_ids=exclude_ids,
        )
        print(format_target_resolution_summary(resolved))
        analyze_target_ids = resolved["target_track_ids"]
        if resolved.get("missing_track_ids"):
            print(f"WARNING: missing tracks in payload: {resolved['missing_track_ids']}", file=sys.stderr)

    body = AnalyzeVideoRequest(
        video_id=video_id,
        user_id=args.user_id,
        match_type=args.match_type,
        target_track_ids=analyze_target_ids,
        debug=args.debug,
        target_label=args.target_label,
        target_jersey_color=args.target_jersey_color,
        target_court_side=args.target_court_side,
    )

    await init_db()
    async with AsyncSessionLocal() as session:
        result = await run_video_analyze(
            session,
            body,
            debug=args.debug,
            target_resolution=resolved,
        )

    print(f"debug_report_id={result.debug_report_id}")
    print(f"valid_gameplay_ratio={result.metrics.segment_filter.valid_gameplay_ratio if result.metrics.segment_filter else 'n/a'}")
    print(f"artifacts: {debug_report_dir(video_id)}")
    return 0


def _check_video_deps() -> None:
    try:
        import cv2  # noqa: F401
    except ImportError as e:
        print(
            "Missing dependency: opencv-python-headless\n"
            "Install: pip install opencv-python-headless ultralytics\n"
            "Or: pip install -r requirements.txt",
            file=sys.stderr,
        )
        raise SystemExit(1) from e


def main() -> int:
    _check_video_deps()
    parser = argparse.ArgumentParser(description="AthleteCore video debug runner")
    parser.add_argument("--video", required=True, help="Path to local .mp4")
    parser.add_argument("--user-id", default="aigerim")
    parser.add_argument("--match-type", choices=["singles", "doubles", "mixed"], default="singles")
    parser.add_argument("--target-track-ids", default="", help="Comma-separated track ids, e.g. 1 or 1,3")
    parser.add_argument("--target-label", default=None)
    parser.add_argument("--target-jersey-color", default=None)
    parser.add_argument("--target-court-side", choices=["near", "far", "unknown"], default=None)
    parser.add_argument("--exclude-track-ids", default="", help="Comma-separated IDs to force-exclude from selector, e.g. 173")
    parser.add_argument("--detect-only", action="store_true")
    parser.add_argument("--debug", action="store_true", help="Write full debug artifacts")
    args = parser.parse_args()

    if args.detect_only:
        return asyncio.run(_run_detect_only(args))
    if not args.debug:
        print("Tip: pass --debug to write full artifact bundle", file=sys.stderr)
    return asyncio.run(_run_analyze(args))


if __name__ == "__main__":
    raise SystemExit(main())
