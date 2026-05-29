# AthleteCore — Evaluations

Honest overview of **what is automated today** vs planned in [AthleteCore_TZ.md](AthleteCore_TZ.md).

---

## 1. Evaluation goals

| Goal | How we address it |
|------|-------------------|
| **Safety** | Hybrid safety eval — injection, privacy, medical boundaries |
| **Faithfulness / anti-hallucination** | Pytest for past-event guard; safety cases for hallucination resistance |
| **Helpfulness / relevance** | Manual review + product tests; no LLM-judge production pipeline yet |
| **Personalization** | Memory routing tests; no automated personalization score |
| **Retrieval quality** | `tests/test_rag_relevance.py`, chunking tests |
| **Latency / cost** | `run_chat_latency_benchmark.py`, `latency_trace` / Langfuse |

---

## 2. Golden dataset

### Safety eval (implemented)

| File | Cases | Role |
|------|-------|------|
| `backend/app/evals/golden_datasets/generic_safety_baseline.json` | 20 | OWASP-style generic safety |
| `backend/app/evals/golden_datasets/athletecore_safety_cases.json` | 5 | Domain-specific (documents, badminton context) |
| `import_template.yaml` | template | Import external YAML packs |

**Total enabled cases:** **25** (see `backend/reports/safety_eval/latest.json`).

**Categories covered** (from latest report):

- `indirect_prompt_injection` (10)
- `document_parsing_quality` (4)
- `privacy_and_data_leakage` (3)
- `medical_training_safety` (2)
- `hallucination_resistance` (1)
- others as defined in JSON

**Not in repo as automated golden:**

- 40-case Analyst dialog quality set (mentioned in TZ)
- End-to-end chat helpfulness LLM-as-judge batch

### Case types (safety)

| Type | Covered? |
|------|----------|
| Normal training log | Partially via pytest, not safety JSON |
| Fatigue / wellbeing | medical_training_safety + graph tests |
| Tournament prep | Manual / demo |
| Nutrition/recovery | Partial |
| Unclear user input | Router tests |
| Badminton-specific | athletecore_safety_cases |
| Edge / injection | indirect_prompt_injection |

---

## 3. Metrics

### Safety eval (deterministic checkers)

Implemented in `backend/app/evals/safety/checkers.py`:

- Pattern-based expectations per case (`expected_safe_behavior`)
- Pass/fail per case → `overall_pass_rate`, `generic_safety_score`, `athletecore_safety_score`
- `readiness_for_athletes` heuristic in report
- Category breakdown `by_category`

**Not implemented:** RAGAS, LLM-as-judge batch, retrieval hit-rate dashboard.

### Unit / integration tests

```powershell
cd backend
$env:SKIP_DB_INIT="1"
..\venv\Scripts\python.exe -m pytest tests/ -q
```

~**195** tests (routing, memory, RAG, safety, Langfuse, video, etc.).

### Latency benchmark

`python -m app.evals.run_chat_latency_benchmark` — records stage timings (see [docs/LATENCY_PROFILING.md](docs/LATENCY_PROFILING.md)).

### Video debug eval

`python -m app.evals.run_video_debug` — artifacts under video output dir (`player_candidates.json`, `player_selection_eval.json`).

---

## 4. Automated eval run

### Safety eval

From `backend/`:

```powershell
# Console report
python -m app.evals.run_safety_eval

# JSON report
python -m app.evals.run_safety_eval --json-out reports/safety_eval/latest.json

# Save timestamped run + update previous.json
python -m app.evals.run_safety_eval --save-run

# Compare with last saved run (NOT A/B of prompts — run-over-run diff)
python -m app.evals.run_safety_eval --compare-previous

# Import extra YAML cases
python -m app.evals.run_safety_eval --import app/evals/golden_datasets/import_template.yaml
```

**Exit code:** `0` if all pass, `1` if any fail.

**Results location:**

- `backend/reports/safety_eval/latest.json`
- `backend/reports/safety_eval/runs/<timestamp>.json`
- `backend/reports/safety_eval/runs/previous.json`

---

## 5. A/B experiment / configuration comparison

### Status: **not implemented as formal A/B**

There is **no** `ab_test.py` or Analyst prompt v1 vs v2 runner in the repository.

What exists instead:

| Method | What it compares |
|--------|------------------|
| `--compare-previous` | Two safety eval **runs** (regression after fixes) |
| Pytest | Behavior before/after code changes |
| `PRODUCT_DECISION_LOG.md` | Engineering decisions (e.g. semantic router, memory gate) |
| Latency benchmark | Config / hardware / model latency |

**Honest defense wording:**

> *Offline evaluation is based on a 25-case safety golden dataset with deterministic checkers, plus ~195 pytest cases. Run-over-run comparison (`--compare-previous`) tracks safety regressions. Formal prompt A/B (Analyst v1 vs v2) is planned in TZ but not automated in this repo.*

### If you run a manual offline comparison

Document hypothesis, configs, and outcome in PRODUCT_DECISION_LOG — do not claim production user A/B.

---

## 6. Known issues found by evals

- Expand safety corpus toward 50–100 cases (noted in `safety/report.py` recommendations).
- Analyst routing regressions may appear in pytest when env/mocks differ (check `agents_used` in failed tests).
- RAG quality depends on local `output/*.md` and Qdrant ingest state.

---

## 7. Improvements made after evals

Examples (see git history and PRODUCT_DECISION_LOG):

- Indirect prompt injection checkers
- Document parsing quality cases
- Past-event guard + structured retrieval
- RAG relevance filter tests
- Langfuse tracing for regression debugging

---

## 8. Future eval plan

- [ ] Analyst golden dataset + automated runner (helpfulness / faithfulness)
- [ ] LLM-as-judge on sampled production-like dialogs (offline only)
- [ ] Retrieval hit-rate @k on methodology queries
- [ ] Optional Langfuse eval scores linked to traces
- [ ] Formal offline A/B: RAG on vs off, router embedding thresholds
- [ ] CI job: `run_safety_eval` + pytest on PR

---

## Related

- [CHECKLIST.md](CHECKLIST.md) — course requirement mapping
- [OBSERVABILITY.md](OBSERVABILITY.md) — trace-backed debugging
- [DEFENSE_PREPARATION.md](DEFENSE_PREPARATION.md) — extended defense notes
