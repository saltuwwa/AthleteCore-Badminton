# AthleteCore — Observability

## 1. Purpose of tracing

- Debug slow `/api/chat` requests (which stage dominates?)
- Verify routing: semantic router → correct agent
- Confirm anti-hallucination: past-event `llm_called=false`
- Inspect memory write background jobs
- Compare token usage when providers return usage metadata

---

## 2. LangSmith / Langfuse setup

| System | Status in repo |
|--------|----------------|
| **Langfuse** | ✅ Implemented |
| **LangSmith** | ❌ Not wired in backend |

### Langfuse configuration

File: `backend/.env` (template: `backend/.env.example`)

```env
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
# or LANGFUSE_BASE_URL=...
LANGFUSE_ENV=development
LANGFUSE_TRACE_VERBOSE=false
LANGFUSE_SAMPLE_RATE=1.0
```

Install: `pip install -r requirements.txt` (includes `langfuse>=2.0.0`).

**Detailed guide:** [docs/LANGFUSE_TRACING.md](docs/LANGFUSE_TRACING.md)

### LangSmith

Not configured. For course defense, present **Langfuse** as the tracing implementation and show real traces from Langfuse Cloud if keys are set.

---

## 3. What is logged

| Signal | Where |
|--------|--------|
| **Request trace** | `start_request_trace` in `main.py` (`api_chat`) |
| **LLM generations** | `record_langfuse_generation` in `llm.py` |
| **Stage spans** | `stage_span` / `langfuse_observation_span` in `latency_trace.py` |
| **Memory write** | `background_write.py`, `extraction.py` |
| **Router fast path** | `semantic_router.py` |
| **Errors** | `record_langfuse_exception` |
| **Dev latency JSON** | `latency_trace` when `DEVELOPMENT_MODE=true` |

Verbose prompt logging: only if `LANGFUSE_TRACE_VERBOSE=true` (privacy caution).

---

## 4. How to view traces

1. Enable Langfuse in `.env`, restart uvicorn.
2. Send chat requests via UI or `POST /api/chat`.
3. Open [Langfuse Cloud](https://cloud.langfuse.com) → project → **Traces**.
4. With `DEVELOPMENT_MODE=true`, API response may include:
   - `langfuse_trace_id`
   - `langfuse_trace_url`

Filter by `LANGFUSE_ENV` tag (e.g. `development`).

---

## 5. Example traced scenario

**Scenario:** User asks about a match that is **not** in memory.

1. Trace name: `api_chat` (or request id).
2. Span: `planner` / semantic routing.
3. Span: `memory_recall` (if routed).
4. Past-event resolution → metadata shows blocked analysis.
5. Generation may be **skipped** or short-circuit reply — check `llm_called` in dev `analyst_trace` if exposed.

**Scenario:** Normal analyst turn

1. Spans: `memory_recall`, `methodology_retrieval`, `analyst` LLM generation.
2. Generation records model id (`claude-sonnet-4-20250514`) and truncated output.

---

## 6. How tracing helped debugging

Documented use cases (engineering):

- Finding dominant latency stage (router vs Analyst vs RAG)
- Confirming memory write runs in background without blocking response
- Verifying Langfuse disabled path does not break chat (tests in `test_langfuse_tracing.py`)

Add your own screenshot examples from Langfuse UI for defense slides.

---

## 7. Local latency trace (complement)

Even without Langfuse, `DEVELOPMENT_MODE=true` returns `latency_trace` in `/api/chat`:

- per-stage milliseconds
- `request_id`
- routing metadata

See [docs/LATENCY_PROFILING.md](docs/LATENCY_PROFILING.md).

Benchmark script:

```powershell
cd backend
python -m app.evals.run_chat_latency_benchmark
```

---

## 8. Limitations

- Sampling: `LANGFUSE_SAMPLE_RATE` < 1.0 drops traces.
- No LangSmith datasets/eval UI integration.
- No Sentry in current backend (errors only in logs + Langfuse exceptions).
- Verbose mode may expose PII — keep off for shared demos.
- Production deployment tracing not fully documented (Render/Vercel are deployment targets in TZ, local demo is primary).

---

## Code map

```
backend/app/observability/langfuse_tracing.py   # client, spans, generations
backend/app/graph/latency_trace.py              # stage_span bridge
backend/app/main.py                             # api_chat trace lifecycle
backend/tests/test_langfuse_tracing.py
```
