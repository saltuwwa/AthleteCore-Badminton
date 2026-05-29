---
name: athletecore
description: "AthleteCore domain skill for a professional badminton athlete AI system. Use when working on AthleteCore code, LangGraph agents (Planner, Analyst, Health Coach, Scheduler), long-term memory (LTM/STM), voice logs, match root-cause analysis, training schedule with HITL, MCP tools (recall_athlete_memory, search_sports_methodology, get_training_schedule, propose_training_block), parsing sports PDFs into output/*.md, FastAPI backend, or React frontend. Triggers on: badminton, AthleteCore, Analyst, спортсменка, матч, подача, footwork, memory gate, LlamaParse, Qdrant RAG, Demo Days."
license: MIT
compatibility: Works with AthleteCore MCP server (mcp_server/server.py) when configured in Cursor. Backend must be runnable for live memory/schedule tools.
metadata:
  author: athletecore-team
  version: "1.0"
---

# AthleteCore

AI career-management for a **professional badminton athlete** (not a generic chatbot).

## Product goals

1. **Root-cause analysis** of match/training errors (patterns, not play-by-play only).
2. **Personal memory** across sessions (LTM) with noise gating — no memory on weather/small talk.
3. **Methodology RAG** from parsed coaching books (`output/*.md`).
4. **Schedule** with **HITL**: AI proposes blocks → `pending_confirmation` → athlete confirms.

## Architecture (quick map)

| Piece | Location |
|-------|----------|
| LangGraph | `backend/app/graph/` — planner → load_memory? → specialist → aggregator |
| LTM | `backend/app/memory/` — extraction, hybrid recall, write-gate |
| MCP tools (shared) | `backend/app/mcp_tools/` |
| MCP server (stdio) | `mcp_server/server.py` |
| Calendar DB | `backend/app/schedule/` |
| Frontend chat | `frontend/src/pages/ChatPage.tsx` |
| PDF → MD | `scripts/parse_badminton_pdf.py` → `output/` |

## When to use MCP tools (Cursor / agents)

Enable **athletecore** MCP and call tools instead of guessing:

| Tool | Use when |
|------|----------|
| `recall_athlete_memory` | Personal history, recurring errors, preferences, past matches |
| `search_sports_methodology` | Technique, footwork, drills — cite `source` filename |
| `get_training_schedule` | Before changing plan — see conflicts and load |
| `propose_training_block` | Adding a block — creates **pending** event (HITL) |

Do **not** use memory tools for off-topic queries (see `references/memory-gate.md`).

## Analyst workflow

Follow `references/analyst-workflow.md`:

- Classify errors: technical / tactical / psychological / physical_fatigue
- Risk: HIGH if ≥3 similar occurrences (check memory + user log)
- End with fenced JSON `errors[]` — backend strips it from UI text; do not duplicate JSON in prose
- Pull methodology via `search_sports_methodology` for footwork/stroke questions

## Scheduler workflow

1. `get_training_schedule` for next 14 days.
2. Respect recovery after MATCH/high intensity.
3. To register a proposal, include line: `PROPOSE: YYYY-MM-DD HH:MM-HH:MM | Title | TRAINING`
4. Tell user that **pending** blocks need confirmation in the app.

## Memory gate (planner)

`needs_memory=true` only when answer needs athlete history (match analysis, weekly plan with load, recurring patterns).

`needs_memory=false` for weather, news, moving a single calendar event without re-planning.

See `references/memory-gate.md`.

## Ingest new coaching PDFs

See `references/rag-ingest.md` — LlamaParse → `output/*.md` → chunks → Qdrant `sports_methodology` (`scripts/ingest_methodology_qdrant.py`).

## Run locally

```bash
# Backend (port 8001 on Windows if 8000 busy)
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001

# Frontend
cd frontend && npm run dev

# MCP (from project root, after pip install mcp)
set PYTHONPATH=backend
python -m mcp_server.server
```

## Code change rules

- Keep **Russian** user-facing copy in UI and agent replies.
- Do not break `memory_gate` — wrong LTM recall hurts trust.
- Schedule proposals must stay `pending_confirmation` until UI confirms.
- Match existing LiteLLM multi-model routing (Planner mini, Analyst Sonnet when key present).

## References

- `references/analyst-workflow.md` — Analyst rubric + JSON schema
- `references/memory-gate.md` — when LTM is loaded
- `references/mcp-tools.md` — tool parameters and examples
- `references/rag-ingest.md` — PDF pipeline and chunking
