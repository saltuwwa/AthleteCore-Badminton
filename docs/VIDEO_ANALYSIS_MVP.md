# Video Analysis MVP

Pose-based match feedback pipeline (no raw video sent to the LLM).

## Pipeline

```text
video upload → YOLO pose + ByteTrack → user selects track_id(s)
  → gameplay segment filter (replays/pauses/coach shots excluded)
  → Python metrics JSON (valid gameplay frames only)
  → LTM episodic (video_analysis) + semantic patterns + baseline
  → Qdrant methodology RAG → Gemini coaching text (compares with past videos)
```

## Gameplay segment filter

Module: `backend/video_analysis/segment_filter.py` (re-export: `backend/app/video_analysis/`).

Before metrics, frames are classified (`gameplay`, `replay`, `closeup`, `coach_or_spectator`, `scoreboard`, `pause`). Only **valid gameplay** frames contribute to speed, fatigue, attack/defense, and team spacing.

Response field: `metrics.segment_filter` with `valid_gameplay_ratio`, `valid_segments`, `ignored_segments`, optional `warning` (RU: «Недостаточно игровых моментов для точного анализа.»).

Eval: `backend/video_analysis/eval_report.py` → `build_video_eval_report()` with `gameplay_segment_precision`, `gameplay_segment_recall`, `ignored_replay_rate`, `invalid_segment_leak_rate`.

Tests: `backend/tests/test_segment_filter.py`, `backend/tests/test_track_postprocess.py`.

Player selection post-processing (`track_postprocess.py`): court-area filter, IoU duplicate merge, near/far side pick (singles → max 2). Debug: `player_selection_eval.json` in debug report folder.

## Eval / Debug mode

Enable with `debug: true` on `POST /video/analyze` or `?debug=true`.

Artifacts: `backend/reports/video_debug/{video_id}/` (01–13 numbered files + index).

API: `GET /video/{video_id}/debug` — full bundle for UI.

Frontend (dev): `/analysis/video/{video_id}/debug` — step-by-step eval view.

CLI:

```powershell
cd backend
python -m app.evals.run_video_debug --video "C:\path\match.mp4" --match-type singles --detect-only
python -m app.evals.run_video_debug --video "C:\path\match.mp4" --user-id aigerim --match-type singles --target-track-ids 1 --debug
```

Production users see only results + gameplay coverage note; enable `localStorage.setItem('video_debug','1')` for eval UI in prod builds.

Raw video is **not** stored in memory — only structured analysis JSON.

## API (prefix `/video`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/video/upload` | multipart file → `video_id` |
| POST | `/video/detect-players` | `{ "video_id", "max_players": 4 }` → preview + 2–4 players |
| POST | `/video/analyze` | `{ "video_id", "user_id", "match_type", "target_track_ids" }` → metrics + coaching + memory_summary |

## LTM integration

After each analyze:

1. **Episodic** `event_type=video_analysis` — payload with metrics, issues, recommendations (no video bytes).
2. Retrieve last **5–10** `video_analysis` for the same `user_id`.
3. **Semantic** (write-gate + confidence ≥ 0.72):
   - `performance.video.repeated_error_pattern`
   - `performance.video.improvement_pattern`
   - `performance.video.athlete_baseline`

Gemini feedback fields: `repeated_mistakes`, `improvements_noted`, `regressions_noted`, `next_training_focus`.

See `backend/app/memory/video_memory_service.py`, `video_patterns.py`, `video_payload.py`.

## Config (`backend/.env`)

- `GOOGLE_API_KEY` — Gemini coaching (not the video)
- `OPENAI_API_KEY` — Qdrant RAG embeddings (existing methodology collection)
- `YOLO_POSE_MODEL` — default `yolov8n-pose.pt`
- `YOLO_TRACKER` — default `bytetrack.yaml`
- `VIDEO_FEEDBACK_MODEL` — default `gemini-2.0-flash`
- `VIDEO_STORAGE_DIR` — default `backend/data/videos`

## Modules

`backend/video_analysis/` — isolated from LangGraph chat.

## Disclaimers

Metrics and coaching use approximate wording only (pose landmarks, visible movement). No shuttle speed, no exact biomechanics.
