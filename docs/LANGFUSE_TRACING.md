# Langfuse tracing — AthleteCore

Langfuse is the **persistent observability layer** for AthleteCore. It complements local `latency_trace` (JSON in dev responses) with dashboard traces across LLM calls, retrieval, guardrails, memory write, and errors.

## What it is used for

- Debug slow `/api/chat` requests (which stage dominates?)
- Verify anti-hallucination behavior (`llm_called=false`, `blocked` tag)
- Inspect semantic router → agent routing regressions
- Monitor memory write background jobs
- Compare token usage / cost per model (when provider returns usage)

## Environment setup

Add to `backend/.env` (see `backend/.env.example`):

```env
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_ENV=development
LANGFUSE_TRACE_VERBOSE=false
LANGFUSE_SAMPLE_RATE=1.0
```

Install dependency:

```powershell
cd backend
pip install -r requirements.txt
```

## Enable locally

1. Create project at [Langfuse Cloud](https://cloud.langfuse.com) (or self-host).
2. Copy public/secret keys into `.env`.
3. Set `LANGFUSE_ENABLED=true`.
4. Restart uvicorn.
5. Send `POST /api/chat` requests.
6. Open Langfuse UI → Traces.

With `DEVELOPMENT_MODE=true`, responses also include:

- `langfuse_trace_id` (same as `latency_trace.request_id`)
- `langfuse_trace_url` (best-effort link)

## Disable

```env
LANGFUSE_ENABLED=false
```

Or omit keys — backend logs a warning once and continues (no crash).

Tests use `LANGFUSE_ENABLED=false` by default via Settings defaults.

## Privacy / verbose mode

| Mode | `LANGFUSE_TRACE_VERBOSE` | What is sent |
|------|--------------------------|--------------|
| Compact (default) | `false` | Message previews, prompt/completion char counts, metadata, structured fields |
| Verbose | `true` | Full chat messages in generation input/output |

**Never logged:** API keys, raw audio, full huge transcripts by default, secrets.

## Trace model

### One `/api/chat` = one trace

- **Name:** `api_chat`
- **ID:** same as `latency_trace.request_id` (correlation)
- **Tags:** `athletecore`, `backend`, `semantic-router-v1`, plus dynamic:
  - `agent:analyst` / `health_coach` / `direct` / `scheduler`
  - `turn_intent:PAST_EVENT_LOOKUP_REQUEST`
  - `blocked` when guardrail blocks Analyst LLM
  - `background_write` when memory write scheduled
  - `fast_path` when general chat fast path used

### Spans (via `stage_span`)

- `request_received`
- `fast_path_general_chat`
- `semantic_router`
- `date_normalizer`
- `structured_retrieval`
- `memory_recall`
- `turn_safety`
- `methodology_rag`
- `agent_llm`
- `response_parsing`
- `response_assembly`
- `graph_invoke`
- `memory_write_background` (separate linked trace)

### Generations (central `llm.acompletion` + memory extraction)

- `semantic_router`
- `analyst` / `health_coach` / `direct` / `scheduler` (via `latency_name`)
- `memory_extraction` (background write path)

Each generation records: model, duration, temperature, token usage (if available), compact I/O unless verbose.

## Example scenarios

### Anti-hallucination (no memory)

**User:** `разбери мою тренировку 10 февраля`

Expected trace:

1. `semantic_router` → `PAST_EVENT_LOOKUP_REQUEST`
2. `date_normalizer` → `2026-02-10`
3. `structured_retrieval` → 0 rows
4. `turn_safety` → `blocked_reason=past_event_not_found`
5. **No** `agent_llm` generation (or skipped)
6. Tags: `blocked`, `turn_intent:PAST_EVENT_LOOKUP_REQUEST`
7. Output metadata: `comparison_status=not_found`, `llm_called=false`

### New event + background write

**User:** `вчера была тренировка: бег 5 км, многоваланка, подвернула голеностоп`

Expected:

1. `semantic_router` → `NEW_EVENT_LOG`, health signal
2. `health_coach` agent generation
3. Tag `background_write`
4. Separate trace `memory_write_background` with `memory_extraction` generation

### Slow request debugging

1. Open trace sorted by `total_latency_ms`.
2. Compare span durations: `semantic_router` vs `agent_llm` vs `methodology_rag`.
3. Check generation token usage for cost spikes.

## Architecture

```
POST /api/chat
  └─ Langfuse trace (api_chat)     ← same request_id as latency_trace
       ├─ spans (stage_span)
       ├─ generations (llm.acompletion)
       └─ metadata from graph result + analyst_trace

Background memory write
  └─ Linked trace (:memory_write)
       └─ memory_extraction generation
```

## Limitations / next steps

- LangGraph node-level auto-instrumentation not enabled (manual spans only).
- Cache hit/miss metadata partial (router TTL cache only via `route_source` meta).
- Trace URL format may vary by Langfuse host/project — use UI search by `request_id`.
- Formal eval runs can add separate traces per eval case (not wired yet).
