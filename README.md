# AthleteCore

**AI-powered sports career assistant for professional badminton athletes.**

AthleteCore is a final project for the **LLM Engineer** course. It demonstrates a production-style LLM product—not a generic chatbot—with LangGraph orchestration, long-term memory, RAG over coaching books, MCP tools, voice input, safety evals, and Langfuse tracing.

Repository: [github.com/saltuwwa/AthleteCore-Badminton](https://github.com/saltuwwa/AthleteCore-Badminton)

---

## Problem

Professional athletes generate rich, unstructured signals every day: match logs, fatigue, technique issues, schedule conflicts, and recovery needs. A one-shot chatbot forgets context, cannot cite coaching methodology, and may hallucinate past events. Athletes need a **memory-driven assistant** that:

- Remembers recurring errors and preferences across sessions
- Grounds advice in parsed coaching literature (not invented drills)
- Routes complex turns to specialized agents (analysis vs schedule vs wellbeing)
- Proposes calendar changes with human confirmation (HITL)

---

## Solution

AthleteCore combines:

| Capability | What it does |
|------------|----------------|
| **Multi-agent LangGraph** | Semantic router → optional LTM recall → Analyst / Health Coach / Scheduler / Direct → Aggregator |
| **Long-term memory (LTM)** | SQLite + embeddings; write-gate; structured sport events; past-event guard |
| **Methodology RAG** | Qdrant `sports_methodology` over `output/*.md` (+ lexical fallback) |
| **Voice logging** | Whisper STT → draft → user sends → graph pipeline |
| **MCP server** | 4 domain tools for Cursor/agents |
| **Custom Skill** | `.agents/skills/athletecore/SKILL.md` |
| **Safety evals** | 25-case golden dataset + deterministic checkers |
| **Observability** | Langfuse traces + dev `latency_trace` |

Demo persona: professional badminton athlete **Aigerim** (course scenario).

---

## Key Features

- Voice logging (`POST /api/transcribe`, Whisper)
- Personalized memory (hybrid recall, supersession, write-gate)
- Match/training analysis (Analyst agent, structured JSON errors)
- RAG-based methodology search (Qdrant + chunking)
- Agent workflow with conditional routing
- MCP tools (memory, RAG, schedule, HITL propose)
- Custom AthleteCore Skill for Cursor
- Hybrid safety evals + Langfuse tracing
- React demo frontend (chat, video, schedule UI)

---

## Demo Flow

1. User opens **Chat** (`/chat`) — backend health shows **CONNECTED**.
2. User records a **voice training/match log** → Whisper transcribes to draft text.
3. User edits and sends → `POST /api/chat` starts LangGraph.
4. **Planner** (semantic router) classifies intent → may **load_memory** from SQLite LTM.
5. **Analyst** (or Health/Scheduler/Direct) runs with memory + optional RAG context.
6. **Aggregator** assembles final reply; background job may **write** new memories (gated).
7. Optional: Scheduler proposes `pending_confirmation` calendar block (HITL).

See [RUNBOOK.md](RUNBOOK.md) and [PRESENTATION_BRIEF.md](PRESENTATION_BRIEF.md) for defense demo scripts.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 19, Vite, TypeScript, Tailwind CSS v4 |
| Backend | FastAPI, SQLAlchemy (async SQLite), LangGraph |
| LLM routing | LiteLLM (`backend/app/graph/llm.py`) |
| Planner / Direct | `gpt-4o-mini` (config: `PLANNER_MODEL`) |
| Analyst | `claude-sonnet-4-20250514` (config: `ANALYST_MODEL`) |
| Embeddings | OpenAI `text-embedding-3-small` (1536d) |
| Vector DB | Qdrant (`sports_methodology`) |
| STT | OpenAI Whisper (`whisper-1`) |
| MCP | FastMCP stdio server (`mcp_server/server.py`) |
| Tracing | **Langfuse** (not LangSmith in current code) |
| Evals | Hybrid safety runner (`backend/app/evals/`) |
| PDF ingest | LlamaParse → `output/*.md` |

---

## Architecture Overview

```
User (text/voice) → FastAPI → LangGraph (planner → memory? → specialist → aggregator)
                              ↓                    ↓              ↓
                         SQLite LTM          Qdrant RAG      MCP tools (optional)
                              ↓
                         Langfuse trace (if enabled)
```

Full diagrams and request lifecycle: **[ARCHITECTURE.md](ARCHITECTURE.md)**

Memory deep dive: **[MEMORY.md](MEMORY.md)** · **[MEMORY_ARCHITECTURE.md](MEMORY_ARCHITECTURE.md)**

---

## Repository Structure

```
.
├── backend/                 # FastAPI, LangGraph, memory, RAG, evals, observability
│   ├── app/graph/           # LangGraph nodes, semantic router, runner
│   ├── app/memory/          # LTM extraction, recall, write-gate
│   ├── app/rag/             # Chunking, Qdrant store, retrieval
│   ├── app/mcp_tools/       # Shared tool implementations
│   ├── app/evals/           # Safety eval golden datasets + runner
│   ├── app/observability/   # Langfuse integration
│   └── video_analysis/      # Video MVP (pose, metrics)
├── frontend/                # React SPA (chat, video, schedule)
├── mcp_server/              # MCP stdio server (4 tools)
├── scripts/                 # PDF parse, Qdrant ingest
├── .agents/skills/athletecore/  # Course custom Skill
├── output/                  # Parsed coaching books (local, not in git)
└── docs/                    # LANGFUSE_TRACING, LATENCY_PROFILING, etc.
```

---

## Quick Start

### Requirements

- Python 3.11+
- Node.js 18+
- API keys: `OPENAI_API_KEY` (required), `ANTHROPIC_API_KEY` (recommended for Analyst)

### Backend

```powershell
git clone https://github.com/saltuwwa/AthleteCore-Badminton.git
cd AthleteCore-Badminton
python -m venv venv
.\venv\Scripts\Activate.ps1

cd backend
copy .env.example .env
# Edit .env with your keys

pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8001
```

Health: http://127.0.0.1:8001/health · API docs: http://127.0.0.1:8001/docs

> On Windows port **8000** is often busy — use **8001**.

### Frontend

```powershell
cd frontend
copy .env.example .env
# VITE_API_PROXY_TARGET=http://127.0.0.1:8001

npm install
npm run dev
```

Open http://localhost:5173 → **Chat** (`/chat`).

Defense slides (PDF): [docs/athletecore_defense_presentation.pdf](docs/athletecore_defense_presentation.pdf)

### Methodology RAG (optional but recommended)

```powershell
docker compose up -d qdrant
cd ..
.\venv\Scripts\python scripts\ingest_methodology_qdrant.py --recreate
```

Verify `/health` → `"methodology_rag": "qdrant"`.

### Evals

```powershell
cd backend
$env:SKIP_DB_INIT="1"
..\venv\Scripts\python.exe -m app.evals.run_safety_eval
```

Details: **[EVALS.md](EVALS.md)**

Full operations: **[RUNBOOK.md](RUNBOOK.md)**

---

## Environment Variables

Template: `backend/.env.example`. Never commit real keys.

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | Whisper, planner, embeddings, direct path |
| `ANTHROPIC_API_KEY` | Analyst (Claude Sonnet) |
| `DATABASE_URL` | SQLite async (`athletecore.db`) |
| `GRAPH_CHECKPOINT_PATH` | LangGraph thread checkpoints |
| `PLANNER_MODEL` / `ANALYST_MODEL` | LiteLLM model IDs |
| `QDRANT_URL`, `METHODOLOGY_*` | RAG collection and chunking |
| `LANGFUSE_*` | Persistent tracing (optional) |
| `DEVELOPMENT_MODE` | Dev traces in `/api/chat` response |
| `WHISPER_MODEL`, `WHISPER_LANGUAGE` | Voice STT |

See `.env.example` for video, document, and recall tuning variables.

---

## Evals and Monitoring

| Doc | Content |
|-----|---------|
| [EVALS.md](EVALS.md) | Golden safety dataset (25 cases), metrics, commands |
| [OBSERVABILITY.md](OBSERVABILITY.md) | Langfuse + latency profiling |
| [docs/LANGFUSE_TRACING.md](docs/LANGFUSE_TRACING.md) | Setup and privacy modes |

---

## Current Status

### Works (real API / code paths)

- Chat LangGraph pipeline with semantic routing and conditional memory load
- LTM read/write with write-gate and past-event guard
- Qdrant methodology RAG (+ lexical fallback)
- Whisper voice transcription
- MCP server with 4 tools
- Safety eval runner (25 cases)
- Langfuse tracing (when enabled)
- Document upload analysis (`/api/documents`)
- Video analysis MVP (pose pipeline)
- ~195 backend pytest tests
- Defense PDF: `docs/athletecore_defense_presentation.pdf`

### Partial / demo / planned

| Area | Status |
|------|--------|
| Schedule / History / Progress / Health UI pages | Static seed data in frontend |
| Analyst golden dataset (40+ cases) | Not implemented as automated runner |
| A/B prompt/model comparison | Not in repo; TZ mentions only |
| LangSmith | Not wired (use Langfuse) |
| Production auth / multi-user | Not implemented |
| BWF scraping in ARCHITECTURE diagram | Aspirational — not in current backend |

---

## Future Roadmap

See **[ROADMAP.md](ROADMAP.md)** — coach dashboard, federation B2B2C, multi-sport, production evals, HITL schedule UI.

---

## Documentation Index

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design, LangGraph, diagrams |
| [MEMORY.md](MEMORY.md) | Memory layer (presentation-friendly) |
| [MEMORY_ARCHITECTURE.md](MEMORY_ARCHITECTURE.md) | Detailed LTM implementation |
| [MCP.md](MCP.md) | MCP server and tools |
| [SKILLS.md](SKILLS.md) | Custom Skill |
| [EVALS.md](EVALS.md) | Evaluation strategy |
| [OBSERVABILITY.md](OBSERVABILITY.md) | Tracing and debugging |
| [PRESENTATION_BRIEF.md](PRESENTATION_BRIEF.md) | Defense slides & Q&A (RU) |
| [RUNBOOK.md](RUNBOOK.md) | Local run & demo checklist |
| [CHECKLIST.md](CHECKLIST.md) | Course requirements matrix |
| [DEFENSE_PREPARATION.md](DEFENSE_PREPARATION.md) | Extended defense notes |

---

## License

Educational final project for LLM Engineer course defense.
