# Latency profiling — `/api/chat`

Instrumentation: `backend/app/graph/latency_trace.py`, wired through graph nodes, `llm.acompletion`, `past_event_guard`, `main.api_chat`.

## Enable

```env
DEVELOPMENT_MODE=true
```

Response includes `latency_trace` (compact: durations, char counts, row counts — no prompts). Backend console prints `[latency]` summary per request.

Frontend (dev): browser console `[chat latency]` with client vs backend timing.

## Manual scenarios

Use a **fresh `thread_id`** per scenario when comparing routes, or accept checkpoint carry-over.

| # | Scenario | Message |
|---|----------|---------|
| 1 | GENERAL_CHAT | `как дела?` |
| 2 | NEW_EVENT_LOG | `вчера была тренировка: бег 5 км, многоваланка, подвернула голеностоп` |
| 3 | PAST_EVENT_LOOKUP found | `разбери мою тренировку которая была 28го мая` |
| 4 | PAST_EVENT_LOOKUP not found | `разбери мою тренировку 10го февраля` |
| 5 | ADVICE_REQUEST | `как восстановиться после того, как подвернула голеностоп?` |

Quick probe (backend on `:8001`):

```powershell
cd backend
$env:DEVELOPMENT_MODE='true'
python -c "import asyncio, httpx, json; ..."
```

---

## Latency profiling report (2026-05-29, local, gpt-4o-mini)

### 1. GENERAL_CHAT — «как дела?»

**Total latency:** 9694 ms  
**Agents:** `direct`

| Stage | ms |
|-------|-----|
| semantic_router | 4037 |
| date_normalizer | 11 |
| agent_llm (direct) | 1526 |
| graph_invoke | 9693 |

**LLM:** semantic_router 4037 ms · direct 1526 ms  
**DB:** —  
**Bottleneck:** semantic router (~42% of total)  
**Note:** No memory recall, no analyst — as expected.

---

### 2. NEW_EVENT_LOG — тренировка + травма

**Total latency:** 14491 ms  
**Agents:** `health_coach`

| Stage | ms |
|-------|-----|
| semantic_router | 2284 |
| memory_recall | 3061 |
| agent_llm (health_coach) | 2407 |
| memory_write | 5134 |
| graph_invoke | 7800 |

**LLM:** semantic_router 2284 ms · health_coach 2407 ms  
**DB:** —  
**Bottleneck:** memory_write cold path (extraction + embeddings + insert) ~35%  
**Note:** Router chose health_coach (injury signal), not analyst.

---

### 3. PAST_EVENT_LOOKUP found — 28 мая

**Total latency:** 21110 ms  
**Agents:** `analyst`

| Stage | ms |
|-------|-----|
| semantic_router | 7189 |
| structured_retrieval | 14 |
| memory_recall | 1451 |
| methodology_rag | 3177 |
| agent_llm (analyst) | 6569 |
| turn_safety | &lt;1 |

**LLM:** semantic_router 7189 ms · analyst 6569 ms  
**DB:** `find_training_by_date` 14 ms, 1 row  
**Bottleneck:** semantic_router + analyst LLM (~66% combined); methodology RAG ~15%

---

### 4. PAST_EVENT_LOOKUP not found — 10 февраля

**Total latency:** 6649 ms  
**Agents:** `analyst` (blocked, no LLM)

| Stage | ms |
|-------|-----|
| semantic_router | 2231 |
| structured_retrieval | 8 |
| memory_recall (semantic fallback) | 1598 |
| agent_llm | 0 |

**LLM:** semantic_router only  
**DB:** `find_training_by_date` 8 ms, 0 rows  
**Bottleneck:** semantic_router + embedding fallback recall  
**Note:** Fast path — no analyst LLM — as expected.

---

### 5. ADVICE_REQUEST — восстановление после голеностопа

**Total latency:** 10470 ms  
**Agents:** `health_coach`

| Stage | ms |
|-------|-----|
| semantic_router | 2463 |
| memory_recall | 1381 |
| agent_llm (health_coach) | 5096 |

**LLM:** semantic_router 2463 ms · health_coach 5096 ms  
**DB:** —  
**Bottleneck:** health_coach LLM (~49%); methodology_rag not used on this path

---

## After optimizations (2026-05-29, Steps 1–4)

Changes: fast-path GENERAL_CHAT, background `memory_write`, methodology RAG gating, safe caches (embedding, methodology, router TTL, date norm).

| Scenario | total_ms (before → after) | semantic_router | agent_llm | memory_write | methodology_rag | Notes |
|----------|---------------------------|-----------------|-----------|----------------|-----------------|-------|
| 1 GENERAL_CHAT | 9694 → **16054*** | 4037 → **0** | 1526 → 4656* | 0 → 0 | 0 → 0 | `route_source=fast_path_general_chat` — router skipped; *agent variance on this run |
| 2 NEW_EVENT_LOG | 14491 → **9238** | 2284 → 2695 | 2407 → 2876 | 5134 → **0** | 0 → 0 | `memory_write_mode=background`, `memory_write_scheduled=true` |
| 3 PAST found | 21110 → **11985** | 7189 → 2296 | 6569 → 5572 | 0 → 0 | 3177 → **0** | `methodology_rag_skipped_reason=past_event_grounded_recap` |
| 4 PAST not found | 6649 → **5646** | 2231 → 2093 | 0 → 0 | 0 → 0 | 0 → 0 | Still no analyst LLM |
| 5 ADVICE | 10470 → 13905* | 2463 → 2481 | 5096 → 8499* | 0 → 0 | 0 → 0 | *LLM latency variance |

**Net wins (stable):** NEW_EVENT_LOG ~5s faster (write off hot path); PAST found ~9s (RAG skipped + router); PAST not found ~1s.

Re-run the 5 scenarios with fresh `thread_id` each time; compare `latency_trace.route_source` and `memory_write_scheduled`.

---

## Cross-cutting findings

| Bottleneck | Typical share | Notes |
|------------|---------------|--------|
| **semantic_router** | 2–7 s every turn | Largest fixed cost; prompt ~2.8k chars |
| **agent_llm** | 0–6.5 s | Zero when past event blocked |
| **memory_write** | 0–5 s | Only `persist_memory` turns |
| **methodology_rag** | 0–3 s | Analyst path with RAG enabled |
| **memory_recall** | 1–3 s | Hybrid + semantic fallback |
| **structured_retrieval** | &lt;15 ms | Not a bottleneck |

**Recommended optimizations (measure first — do not cache yet):**

1. Shorter / cached semantic router for obvious GENERAL_CHAT (see candidates below).
2. Parallelize semantic router + cheap heuristics pre-check (only if safe).
3. Async or deferred memory_write for NEW_EVENT_LOG (return response before cold-path commit).
4. Methodology RAG: embedding cache or smaller top_k when latency matters.
5. Consider faster planner model or prompt compression for router only.

---

## Cache candidates (not implemented)

**Safer:**

1. Date normalization — same text + reference date  
2. Embedding cache — same memory/query text  
3. Methodology RAG — same advice query  
4. Semantic router — exact same user message, short TTL only  
5. Structured retrieval — `user_id` + event_type + event_date; invalidate on memory write  
6. Model response cache — generic advice only, not personal analysis  

**Dangerous:**

- Full `/api/chat` response cache for personal / past-event queries (memory and `not_found` go stale).

Always key user-specific caches with `user_id` / `thread_id` and explicit invalidation.
