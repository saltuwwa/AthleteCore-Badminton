# AthleteCore Product Decision Log

## Purpose

This document tracks important product, UX, architecture, and implementation decisions in AthleteCore.

It explains not only what changed, but also:

- what problem we noticed
- why the old behavior was bad
- what alternatives we considered
- what decision we made
- why this decision is better
- what files or modules changed
- how to verify the change
- what remains unresolved

This is a working product journal and roadmap history, not a final README.

For **current** setup and run instructions, see [`README.md`](README.md).  
For **memory/retrieval architecture only**, see [`MEMORY_ARCHITECTURE.md`](MEMORY_ARCHITECTURE.md).

---

## How to use this log

After every meaningful implementation pass, add a new entry.

A meaningful change can be:

- UI/UX improvement
- bug fix
- agent behavior change
- memory/retrieval change
- prompt or guardrail change
- backend API change
- database/schema change
- transcription/voice flow change
- video analysis flow change
- calendar/MCP change
- testing/evals change
- deployment/config change
- decision to keep or reject a feature

Do not only write “fixed bug”. Always explain:

1. What was wrong before?
2. Why did we decide to change it?
3. What exactly changed?
4. Why is the new behavior better?
5. How can we test it?

**Rule:** If a feature was changed, rejected, postponed, or reverted — document it here.  
Goal: answer *“What did we change, why, what was wrong before, why is the new version better, and what remains?”*

---

## Timeline

### Step 0 — Initial audit and product direction

**Status:** completed  
**Date:** 2026-05  
**Area:** docs

**Problem:**  
AthleteCore already had multiple parts: chat, Analyst agent, memory, calendar, methodology RAG, voice input, history UI, and video analysis. Product decisions were scattered across chat messages and code changes.

**Why this was a problem:**  
It was hard to remember why a feature was changed, why a specific behavior was rejected, or what still needed to be fixed.

**Options considered:**

1. Only update README when something ships.
2. Only technical docs per subsystem (memory, video, etc.).
3. **Single product decision log** (chosen).

**Decision:**  
Create this `PRODUCT_DECISION_LOG.md` as a single source of history for product and implementation decisions.

**Change made:**  
New file at repo root; MEMORY_ARCHITECTURE.md remains memory-specific; README stays “how to run now”.

**Files changed:**

- `PRODUCT_DECISION_LOG.md`

**Why this is better:**  
Reasoning history is preserved across UX, agents, memory, and infra — not only final code state.

**Manual verification:**  
Open this file after each sprint and confirm the latest step is documented.

**Remaining issues:**  
Discipline required: every meaningful pass must add an entry.

**Next step:**  
Keep logging Steps 1+ as they land; do not duplicate full memory design here (link to MEMORY_ARCHITECTURE §14).

---

### Step 1 — Voice transcription UX

**Status:** completed  
**Date:** 2026-05  
**Area:** frontend / UX

**Problem:**  
After recording voice, the UI looked empty and the user could not tell whether transcription was still processing.

**Old behavior:**

- User records voice → recording stops → little or no feedback.
- User may think the app is broken.
- Transcribed text sometimes appeared in a separate “draft” chat bubble instead of the normal input field.

**Why this was a problem:**  
Voice is a primary input for athletes logging long training/match descriptions. Opaque processing breaks trust and blocks edit-before-send.

**Options considered:**

1. Auto-send immediately after transcription (no review).
2. Show transcript only in a green draft bubble in the message list.
3. **Show “Транскрибируется…” then fill the textarea** (chosen).

**Decision:**

- Show a small **«Транскрибируется…»** state after recording stops.
- After transcription finishes, insert text into the **normal message input** (editable).
- User sends manually (unless `autoSendAfterVoice` is enabled elsewhere).

**Change made:**

- Removed draft-bubble voice UX from chat flow.
- Mic disabled while transcribing; loading line visible in composer.

**Files changed:**

- `frontend/src/components/chat/ChatInput.tsx`
- `frontend/src/hooks/useVoiceRecorder.ts`
- `frontend/src/hooks/useChat.ts`
- `frontend/src/pages/ChatPage.tsx`
- `frontend/src/api/transcribe.ts`

**Why this is better:**  
Clear processing feedback; transcript is editable in one place before send; matches familiar chat-app patterns.

**Manual verification:**

1. Record a voice message.
2. Stop recording.
3. Confirm **«Транскрибируется…»** appears.
4. Confirm final transcript appears in the **input field**, not as a separate chat bubble.
5. Edit if needed, then send manually.

**Tests:**  
Manual UI only (no dedicated E2E yet).

**Remaining issues:**

- No in-composer partial transcript streaming (all-or-nothing after Whisper).

**Next step:**  
Optional: show waveform or elapsed time while recording.

---

### Step 2 — Auto-growing chat input

**Status:** completed  
**Date:** 2026-05  
**Area:** frontend / UX

**Problem:**  
The message input was too small for long athlete logs (10–50 sentences from dictation).

**Old behavior:**

- Fixed-height textarea.
- Long transcript hard to review and correct.
- Layout could feel cramped.

**Why this was a problem:**  
Athletes need to review RPE, duration, and errors before sending; a tiny box increases mistakes and abandonment.

**Options considered:**

1. Open modal editor for long voice results.
2. Separate “log editor” page.
3. **Auto-resize textarea with max-height + internal scroll** (chosen, ChatGPT-style).

**Decision:**

- Textarea grows from ~40px up to ~220px.
- Beyond max height: internal scroll; send/mic stay aligned.

**Files changed:**

- `frontend/src/components/chat/ChatInput.tsx` (`TEXTAREA_MIN_PX`, `TEXTAREA_MAX_PX`, `adjustTextareaHeight`)

**Why this is better:**  
One control for short and long input; no mode switch for voice vs typing.

**Manual verification:**

1. Paste a long training description.
2. Input grows with content.
3. After max height, internal scroll appears.
4. Send and mic buttons remain aligned.

**Tests:**  
Manual UI.

**Remaining issues:**

- Mobile keyboard + max-height tuning not validated on all devices.

**Next step:**  
None required for MVP.

---

### Step 3 — Analyst hallucination prevention for past events

**Status:** completed  
**Date:** 2026-05  
**Area:** agents / backend / guardrails

**Problem:**  
For queries like «Разбери мою последнюю тренировку» or «Сравни с матчем 15 апр», Analyst generated plausible but **fake** analysis when no real match/training existed in memory.

**Old behavior:**

- Invented fatigue, tactics, psychology, technical mistakes.
- HIGH/MED structured cards without underlying user data.
- Comparison flow could run Analyst LLM even when LTM had no matching event.

**Why this was a problem:**  
Professional athletes will stop trusting a coach product that confidently lies about sessions that never were logged.

**Options considered:**

1. Prompt-only: “do not invent” (weak; already insufficient).
2. Post-hoc disclaimer on every Analyst message.
3. **Structured guard: SQL memory first → honest not-found → skip LLM** (chosen).
4. Reject all past-tense questions (too harsh).

**Decision:**

- Any request about a **past sport event** must be grounded:
  - detect `is_past_event_request` (analyze / compare / recall / errors / progress + temporal signals);
  - if user provided **concrete facts in this message** → allow LLM with inline grounding only;
  - else **structured SQL retrieval** → semantic fallback;
  - if no record → **do not call Analyst LLM**; honest missing-data reply; `analysis: null`; action buttons (add event / open history).

**Change made:**

- Generalized `past_event_guard.py` (not only “сравни”).
- Wired in `graph/nodes.py` before Analyst `acompletion`.
- Chat actions on not-found; comparison status in API response.

**Files changed:**

- `backend/app/memory/past_event_intent.py`
- `backend/app/memory/past_event_guard.py`
- `backend/app/graph/nodes.py`
- `backend/app/graph/prompts.py` (guardrails)
- `frontend/src/components/chat/AnalystReport.tsx`, `Message.tsx`, `chatMappers.ts`
- `backend/tests/test_past_event_guard.py`
- `backend/tests/test_match_comparison.py`

**Why this is better:**  
Honest-by-default: “нет данных” beats a beautiful fake debrief.

**Manual verification:**

1. Empty or no relevant LTM for user.
2. Ask: **«Разбери мою последнюю тренировку»**.
3. Expected: no Analyst LLM (with `DEVELOPMENT_MODE=true`, `analyst_trace.llm_called === false`).
4. No HIGH/MED cards; message explains missing saved training; buttons to add description.

**Tests:**

```bash
cd backend && python -m pytest tests/test_past_event_guard.py tests/test_match_comparison.py -q
```

**Before behavior:**  
Analyst prose + JSON errors invented from priors.

**After behavior:**  
Not-found template + `chat_actions`; optional grounding block only when memory hit exists.

**Remaining issues:**

- `/history` UI still mock — user cannot yet visually confirm what LTM contains (see Step 5).

**Next step:**  
Grounded suggestions in chat (`GET /api/chat/suggestions`) already partially tied to real memory; expand as LTM fills.

---

### Step 4 — Memory architecture improvement (structured LTM)

**Status:** completed  
**Date:** 2026-05  
**Area:** memory / backend / database

**Problem:**  
Memory stored sport events mostly as text/paraphrases. No reliable `event_date`, `raw_user_text`, `source`, or structured `facts`. Relative phrases like «вчера» stayed in `value` only.

**Old behavior:**  
On 29 May, «вчера была тренировка» could be stored with «вчера» in summary text and **no** `event_date = 2026-05-28`.

**Why this was a problem:**

- Retrieval could not sort/filter “last training” by calendar date.
- Past-event guard had nothing precise to attach analysis to.
- Extractor sometimes saw **user + assistant** in one prompt → risk of saving Analyst output as facts.

**Options considered:**

1. Only improve prompts (insufficient).
2. Separate `events` table (heavier migration).
3. **Extend `memories` + migration + write/read pipeline** (chosen for MVP SQLite).

**Decision:**  
Structured sport memory on existing `memories` table:

| Layer | What |
|--------|------|
| **Write** | user-only extraction; date normalizer; strict `MemoryWriteGate`; `source` column |
| **Read** | SQL-first `structured_retrieval.py`; semantic fallback; `past_event_guard` |
| **Docs** | `MEMORY_ARCHITECTURE.md` §13–14 Implemented fixes |

**Sub-decisions (same pass):**

| Topic | Decision |
|--------|----------|
| Date phrases RU/EN | `date_normalizer.py` + `event_date_confidence` in `facts` |
| Assistant in LTM | Block `source=assistant`; allow `confirmed_analysis` after explicit user confirmation |
| Write allowlist | `memory_classification.py` + categories (match_log, training_log, goal, …) |
| Missing date on episodic | `pending_unresolved_date` or reject; excluded from `find_last_training` SQL |
| Dev observability | `DEVELOPMENT_MODE` → `analyst_trace` on `/api/chat` |

**Files changed (main):**

- `backend/app/memory/models.py`, `migrate.py`, `database.py`
- `backend/app/memory/date_normalizer.py`, `confirmation.py`
- `backend/app/memory/extraction.py`, `write_enrichment.py`, `write_gate.py`, `memory_classification.py`
- `backend/app/memory/structured_retrieval.py`, `past_event_guard.py`, `past_event_intent.py`, `retrieval_trace.py`
- `backend/app/memory/supersession.py`, `constants.py`
- `backend/app/graph/runner.py`, `main.py`
- `backend/app/graph/analyst_trace.py`, `nodes.py`
- `backend/app/config.py` (`memory_timezone`, `development_mode`)
- `MEMORY_ARCHITECTURE.md`
- Tests: `test_date_normalizer.py`, `test_extraction.py`, `test_write_gate.py`, `test_structured_memory_write.py`, `test_structured_retrieval.py`, `test_past_event_guard.py`, `test_analyst_trace.py`

**Why this is better:**  
Write path normalizes time and source; read path queries by `event_date` and `session_type` before vectors; Analyst only runs when data exists or user supplied facts inline.

**Manual verification:**

1. Reference date **2026-05-29** (turn timestamp / timezone `Asia/Almaty`).
2. User writes: **«Вчера была тренировка, 90 минут, RPE 7»**.
3. Inspect DB or API memory row:
   - `created_at` ≈ 2026-05-29
   - `event_date` = **2026-05-28**
   - `raw_user_text` = original message
   - `source` = `user`
   - `event_type` = `training_log`
4. Ask **«Разбери последнюю тренировку»** → should find row and ground Analyst.

**Tests:**

```bash
cd backend && python -m pytest tests/test_date_normalizer.py tests/test_extraction.py tests/test_write_gate.py tests/test_structured_memory_write.py tests/test_structured_retrieval.py tests/test_past_event_guard.py tests/test_analyst_trace.py -q
```

**Before behavior:**  
Text-only `value`; relative dates not queryable; broad write gate.

**After behavior:**  
Structured episodic rows; SQL `ORDER BY event_date DESC`; honest not-found when empty.

**Remaining issues:**

- Existing DB rows pre-migration may lack `event_date` until re-logged or backfilled.
- `pending_unresolved_date` rows need UI label if shown in history.

**Next step:**  
Step 5 — wire `/history` to backend.

---

### Step 5 — History page source of truth

**Status:** planned  
**Date:** —  
**Area:** frontend / backend

**Problem:**  
The `/history` page uses **mock** frontend data, not real backend LTM.

**Old behavior:**  
User may see history entries that are not connected to saved `memories` rows.

**Why this was a problem:**  
Breaks trust after Step 3–4: chat says “add to history” but History page does not reflect truth.

**Options considered:**

1. Keep mock for demo only (document clearly).
2. **GET `/users/{user_id}/memories`** → History UI (chosen direction).
3. Duplicate store in localStorage (rejected).

**Decision:**  
Eventually connect `/history` to backend memory records (filter by `session_type`, sort by `event_date`).

**Change made:**  
None yet (documented as gap).

**Files changed:**

- TBD — expected: `frontend/src/pages/History.tsx`, `frontend/src/data/historyData.ts` (remove or fallback), `backend/app/main.py` (list endpoint already partial via memories API)

**Why this is better (when done):**  
User inspects real sport logs; aligns with Analyst retrieval and not-found actions.

**Manual verification (when implemented):**

1. Save a real training log via chat.
2. Open `/history`.
3. Training appears from backend with correct `event_date` and summary.

**Tests:**  
TBD — API contract test + UI smoke.

**Remaining issues:**  
**Blocked on implementation** — highest-impact UX gap after memory v1.

**Next step:**  
Implement History list consuming `GET /api/users/{user_id}/memories` (or dedicated `/history` endpoint).

---

### Step 6 — Analyst trace and no-memory / no-LLM invariant

**Status:** completed  
**Date:** 2026-05  
**Area:** backend / agents / developer experience / tests

**Problem:**  
When Analyst hallucinated on past events, it was hard to tell whether the answer came from structured memory, semantic fallback, mock data, or pure LLM generation.

**Old behavior:**  
Only server logs; no per-turn proof of grounding; Analyst could still run when LTM had no matching event.

**Decision:**  
Add development-mode `analyst_trace` on every Analyst `/api/chat` turn when `DEVELOPMENT_MODE=true`, and enforce invariant:

> `is_past_event_request` + `retrieved_memory_items.count == 0` + `inline_facts_in_message == false` → **`llm_called` must be `false`**

**Why this is better:**  
We can debug grounding in JSON. The product can prove whether analysis used real memory, inline facts in the current message, or was blocked because no data exists.

**Files changed:**

- `backend/app/memory/retrieval_trace.py`
- `backend/app/memory/past_event_guard.py`
- `backend/app/graph/analyst_trace.py` (`assert_past_event_llm_invariant`, trace fields)
- `backend/app/graph/nodes.py`, `runner.py`
- `backend/app/schemas.py`
- `backend/.env.example`

**Manual verification:**  
`DEVELOPMENT_MODE=true` → `POST /api/chat` → inspect `analyst_trace` (`structured_retrieval_used`, `retrieved_memory_items`, `llm_called`, `blocked_reason`).

**Tests:**

- `tests/test_analyst_trace.py` — required trace fields + **hard invariant regression**
- `tests/test_analyst_trace_validation.py` — 5 scenario validation pass (empty memory, vague past, inline facts, saved training, wrong date)
- Plus structured retrieval / guard suites (`test_structured_retrieval_anti_hallucination.py`, `test_past_event_guard.py`, …)

**Remaining risks:**

- Full regression needed after further memory schema / date normalization / retrieval changes
- Frontend “Show trace” dev panel not implemented (trace is API-only today)

**Next step:**  
Optional dev UI panel; wire History API (Step 5).

---

### Step 7 — Automated anti-hallucination tests (structured retrieval + past-event guard)

**Status:** completed  
**Date:** 2026-05-29  
**Area:** backend / memory / retrieval / tests

**Problem:**  
Structured retrieval and the past-event honest guard were verified manually. Regressions (wrong date accepted, pending null `event_date` treated as “last training”, Analyst calling LLM with empty LTM) were easy to reintroduce without a fixed test matrix.

**Old behavior:**  
Scattered unit tests for SQL helpers and a few guard cases; no single suite mapping product scenarios to trace fields (`structured_retrieval_used`, `llm_called`, `blocked_reason`).

**Decision:**  
Add an explicit pytest matrix that encodes the six product scenarios (empty memory, latest training, exact/wrong date, null-date pending, yesterday) plus Analyst early-exit when memory is missing.

**Change made:**

- `structured_function_called` on retrieval trace; `structured_retrieval_used` means “SQL path attempted”, not only “row found”.
- Pending rows (`event_date IS NULL`, low-confidence fallback) no longer ground `last_training` / dated analyze intents — `blocked_reason=pending_event_date_unknown`, `llm_allowed=false`.
- New file `backend/tests/test_structured_retrieval_anti_hallucination.py` with trace assertions and `analyst_node` check (`analysis: null`, no fake HIGH/MED copy).

**Files changed:**

- `backend/app/memory/past_event_guard.py`
- `backend/app/graph/analyst_trace.py`
- `backend/tests/test_structured_retrieval_anti_hallucination.py`
- `backend/tests/test_analyst_trace.py`

**Why this is better:**  
CI can prove the system does not hallucinate past events; each test name documents which failure mode is blocked.

**Tests (run from `backend/`):**

```bash
python -m pytest tests/test_structured_retrieval_anti_hallucination.py tests/test_structured_retrieval.py tests/test_past_event_guard.py tests/test_analyst_trace.py -q
```

**Anti-hallucination proofs (new tests):**

| Test | Proves |
|------|--------|
| `test_empty_memory_blocks_llm_and_skips_analysis_cards` | Empty LTM → SQL attempted, 0 items, `llm_allowed=false`, Analyst `analysis=null` |
| `test_latest_training_sql_returns_newest_event_date` | Two trainings → `find_last_training` picks 2026-05-28 |
| `test_exact_date_match_april_15` | “15 апреля” → exact `2026-04-15`, not fuzzy |
| `test_wrong_date_does_not_accept_nearby_match` | DB 16th ≠ query 15th → not found, `llm_called=false` |
| `test_null_event_date_pending_not_treated_as_dated_training` | NULL date → pending trace, no LLM grounding |
| `test_yesterday_resolves_to_previous_calendar_day` | Ref 2026-05-29 + “вчера” → 2026-05-28 row |

**Next step:**  
Extend matrix for compare-two-matches and progress-review intents; wire History API (Step 5).

---

### Step 8 — Runtime hallucination fix (UI `/chat` vs unit tests)

**Status:** completed  
**Date:** 2026-05-29  
**Area:** backend / frontend / memory / retrieval

**Problem:**  
Unit tests passed (`analyst_node` + in-memory DB), but real `/chat` still showed fake Analyst cards (физическая усталость / тактический разрыв / HIGH·MED) for “Разбери последнюю тренировку” and dated training queries.

**Root causes (confirmed):**

1. **Date parsing gap:** `10го апреля` was not parsed → intent `analyze_past` fell back to `find_last_training` (any LTM row) or LLM without exact date.
2. **Training day/month:** day+month intent always used `find_match_by_day_month` even for “тренировку …”.
3. **Runtime safety net missing:** path to `acompletion` could still run if early-return conditions were incomplete; `assert_past_event_llm_invariant` was not enforced before LLM.
4. **session_id mismatch risk:** graph nodes defaulted to `"default"` while API/frontend use `"main"`.
5. **Frontend:** `useChat` could still map `analysis` when `comparison_status=not_found`; `AnalysisBlock` showed **demo** HIGH/MED rows when `live` and empty errors.

**Fixes:**

- `date_normalizer`: pattern `10го апреля`
- `past_event_guard`: training day/month lookup; no “last event” fallback when calendar fragment unresolved
- `nodes.py`: invariant assert + final guard before LLM; `session_id` default `main`; block when `db_session` missing
- `useChat.ts`: clear analysis rows / structured report on `not_found`
- `AnalysisBlock.tsx`: no demo cards when `live=true`
- `tests/test_api_chat_past_event.py`: integration via `run_chat_graph` (same as `/api/chat`)

**Manual verification:**  
`DEVELOPMENT_MODE=true` in `backend/.env`, restart uvicorn, send the 3 repro messages on `/chat`; expect `analyst_trace.llm_called=false`, `analysis=null`, honest text only.

---

### Step 10 — LLM semantics vs backend truth (semantic router)

**Status:** completed  
**Date:** 2026-05-29  
**Area:** agents / memory / retrieval

**Problem:**  
Phrase-based routing and guards were brittle: honest `not_found` when the user described a new workout, or fake analysis when memory was empty. Dates like «вчера» had to be calendar-correct across month boundaries.

**Decision:**  
Split responsibilities explicitly:

- **LLM decides what the user means** — `semantic_router` classifies `turn_intent`, `memory_action`, inline facts, recommended agent.
- **Backend decides what is allowed and what data is true** — `turn_safety` invariants, `past_event_guard`, `date_normalizer` (real `datetime`/`zoneinfo`, not LLM dates), structured retrieval, response assembly without stale checkpoint output.

**Key modules:**  
`semantic_router.py`, `turn_safety.py`, `date_normalizer.py`, `past_event_guard.py`, `response_assembly.py`, `state_utils.py`

**Tests:**  
`test_semantic_router.py`, `test_date_normalizer.py` (8 calendar cases), `test_api_chat_past_event.py`

---

## Rejected / postponed ideas

| Idea | Verdict | Reason |
|------|---------|--------|
| Save full assistant analysis to LTM by default | **Rejected** | Pollutes LTM; only user-confirmed coach output (`confirmed_analysis`). |
| Auto-send voice transcript without review | **Postponed** | `autoSendAfterVoice` exists but default is manual send for trust. |
| Separate vector DB for athlete LTM on MVP | **Postponed** | SQLite + JSON embeddings sufficient; Qdrant reserved for methodology. |
| Regex-only past-event detection | **Rejected** | `past_event_intent.py` uses structured marker layers; regex only for dates in text. |

---

## Entry template

Use this template for every new product or implementation decision:

### Step X — [Short title]

**Status:** planned / completed / partial / blocked / reverted  

**Date:**  
**Branch/commit:**  

**Area:** frontend / backend / agents / memory / retrieval / UX / video / calendar / deployment / tests / docs  

**Problem:**  
What was wrong before?

**Old behavior:**  
How did the product behave before?

**Why this was a problem:**  
Why did this hurt UX, correctness, trust, performance, or maintainability?

**Options considered:**

1. …
2. …
3. …

**Decision:**  
What did we decide to do?

**Change made:**  
What exactly changed?

**Files changed:**

- …

**Why this is better:**  
Why is the new behavior better than before?

**Manual verification:**  
How can we check it manually?

**Tests:**  
What tests were added or should be run?

**Before behavior:**  
…

**After behavior:**  
…

**Remaining issues:**  
…

**Next step:**  
…

**Notes:**  
Any important context, tradeoffs, or future ideas.

---

## Quick links

| Document | Purpose |
|----------|---------|
| [`README.md`](README.md) | How to run the project **now** |
| [`MEMORY_ARCHITECTURE.md`](MEMORY_ARCHITECTURE.md) | Memory write/read design and audit |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Overall system architecture |
| `backend/.env.example` | Config flags (`DEVELOPMENT_MODE`, `memory_timezone`, …) |

---

---

## Step 11 — Context-aware follow-up confirmations

**Problem:**  
Short user replies like «да» after a Health Coach yes/no offer were routed as `GENERAL_CHAT` → `direct` (“Привет! Как я могу помочь?”), losing thread context.

**Decision:**  
Store structured `pending_followup` in graph checkpoint (per `thread_id`) when assistant ends with a yes/no offer. Before semantic router, resolve short confirmations/rejections against pending state (`FOLLOWUP_CONFIRMATION` / `FOLLOWUP_REJECTION`). Topic change clears pending and runs normal routing. Bare «да» without pending → `FOLLOWUP_CLARIFICATION` (ask what they mean).

**Why better:**  
Chat feels conversational and coherent; recovery/error breakdown offers actually continue when the athlete says yes.

**Manual verification:**  
1. Turn 1: «как восстановиться после того, как подвернула голеностоп?» → Health Coach ends with «(да/нет)».  
2. Turn 2: «да» → structured recovery breakdown, not generic greeting.  
3. Turn 2: «нет» → polite close.  
4. New thread «да» → clarification question.

**Tests:**  
`backend/tests/test_chat_followup.py` (two-turn graph path).

**Before behavior:**  
«да» → `GENERAL_CHAT` / direct greeting.

**After behavior:**  
«да» with pending offer → same agent continues planned breakdown; pending cleared after consume.

**Remaining issues:**  
Router cache TTL may still classify unrelated short replies if pending was not saved (e.g. checkpoint lost).

**Next step:**  
Optional: persist pending offer text in LTM for cross-session resume.

---

---

## Step 12 — Production-grade Langfuse tracing

**Status:** completed  
**Date:** 2026-05-29  
**Area:** observability / backend

**Problem:**  
Local `latency_trace` JSON (dev-only) is useful for one-off debugging but not enough for real observability. We need persistent traces across LLM calls, retrieval, guardrails, latency, memory write, and errors — especially to catch anti-hallucination regressions.

**Decision:**  
Add **Langfuse** as a real observability layer via `backend/app/observability/langfuse_tracing.py`:

- One `api_chat` trace per request (id = `request_id` from `latency_trace`)
- Spans wired through existing `stage_span()` (no duplicate instrumentation at every call site)
- Generations in central `llm.acompletion` + `memory/extraction.py`
- Background memory write → linked trace `memory_write_background`
- Safe no-op when `LANGFUSE_ENABLED=false` or keys missing

**Why better:**  
Dashboard traces for latency, routing, guardrail blocks (`blocked` tag), token usage, and linked background writes — without removing `latency_trace`.

**Files changed:**

- `backend/app/observability/langfuse_tracing.py`
- `backend/app/config.py`, `backend/.env.example`
- `backend/app/graph/llm.py`, `latency_trace.py`, `main.py`, `nodes.py`, `semantic_router.py`
- `backend/app/memory/background_write.py`, `extraction.py`
- `backend/app/schemas.py`
- `backend/requirements.txt` (`langfuse>=2.0.0`)
- `backend/tests/test_langfuse_tracing.py`
- `docs/LANGFUSE_TRACING.md`

**Privacy:**  
`LANGFUSE_TRACE_VERBOSE=false` (default) → previews only; full prompts only when verbose enabled.

**Manual verification:**

1. Set Langfuse keys + `LANGFUSE_ENABLED=true`
2. `POST /api/chat` with past-event not_found → trace shows `blocked`, no analyst generation
3. `DEVELOPMENT_MODE=true` → response includes `langfuse_trace_id` / `langfuse_trace_url`

**Tests:**

```bash
cd backend
$env:SKIP_DB_INIT="1"
python -m pytest tests/test_langfuse_tracing.py tests/test_api_chat_past_event.py tests/test_structured_retrieval_anti_hallucination.py -q
```

**Remaining issues:**

- Optional: LangGraph `@observe` for automatic node spans
- Eval runner separate traces not wired yet

---

*Last updated: Step 12 Langfuse tracing (2026-05-29).*
