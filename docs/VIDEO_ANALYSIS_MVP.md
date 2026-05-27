# Video Analysis MVP

Pose-based match feedback pipeline (no raw video sent to the LLM).

## Pipeline

```text
video upload → YOLO pose + ByteTrack → user selects track_id(s)
  → Python metrics JSON
  → LTM episodic (video_analysis) + semantic patterns + baseline
  → Qdrant methodology RAG → Gemini coaching text (compares with past videos)
```

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
