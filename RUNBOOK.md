# AthleteCore — Runbook

Local operations and demo-day checklist.

---

## 1. Prerequisites

- Python 3.11+, Node 18+
- `OPENAI_API_KEY` in `backend/.env`
- `ANTHROPIC_API_KEY` recommended for Analyst
- Optional: Docker for Qdrant, Langfuse keys

---

## 2. First-time setup

```powershell
cd "c:\Users\user\Downloads\LLM_Course\Final Project"
python -m venv venv
.\venv\Scripts\Activate.ps1

cd backend
copy .env.example .env
# Edit keys

pip install -r requirements.txt

cd ..\frontend
copy .env.example .env
npm install
```

Methodology (optional):

```powershell
# Parse PDF (needs LLAMA_CLOUD_API_KEY)
cd scripts
pip install -r requirements-parse.txt
python parse_badminton_pdf.py --pdf "..\book sources\<file>.pdf"

# Qdrant
cd ..
docker compose up -d qdrant
.\venv\Scripts\python scripts\ingest_methodology_qdrant.py --recreate
```

---

## 3. Run backend

```powershell
cd backend
..\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
```

| URL | Check |
|-----|-------|
| http://127.0.0.1:8001/health | `status` ok, `methodology_rag` |
| http://127.0.0.1:8001/docs | Swagger |

---

## 4. Run frontend

```powershell
cd frontend
npm run dev
```

| URL | Page |
|-----|------|
| http://localhost:5173/chat | Live chat |
| `docs/athletecore_defense_presentation.pdf` | Defense slides (PDF) |
| http://localhost:5173/home | Dashboard |

`frontend/.env`:

```env
VITE_API_PROXY_TARGET=http://127.0.0.1:8001
```

---

## 5. Run MCP server

For Cursor (also via `.cursor/mcp.json`):

```powershell
cd "c:\Users\user\Downloads\LLM_Course\Final Project"
$env:PYTHONPATH="backend"
.\venv\Scripts\python.exe -m mcp_server.server
```

Restart Cursor after config changes → enable **athletecore** MCP.

---

## 6. Run evals

```powershell
cd backend
$env:SKIP_DB_INIT="1"

# Safety (25 cases)
..\venv\Scripts\python.exe -m app.evals.run_safety_eval

# With JSON + historical compare
..\venv\Scripts\python.exe -m app.evals.run_safety_eval --json-out reports/safety_eval/latest.json --save-run

# All unit tests
..\venv\Scripts\python.exe -m pytest tests/ -q

# Latency benchmark (needs running server)
..\venv\Scripts\python.exe -m app.evals.run_chat_latency_benchmark
```

---

## 7. Check tracing

1. Set in `backend/.env`:
   ```env
   LANGFUSE_ENABLED=true
   LANGFUSE_PUBLIC_KEY=...
   LANGFUSE_SECRET_KEY=...
   DEVELOPMENT_MODE=true
   ```
2. Restart backend.
3. Send a chat message.
4. Open Langfuse UI → Traces.
5. Optional: read `langfuse_trace_url` from API JSON response.

Guide: [docs/LANGFUSE_TRACING.md](docs/LANGFUSE_TRACING.md)

---

## 8. Common errors

| Symptom | Fix |
|---------|-----|
| Frontend DISCONNECTED | Backend not on 8001; check `VITE_API_PROXY_TARGET` |
| Analyst weak / error | Set `ANTHROPIC_API_KEY`; check LiteLLM logs |
| No methodology citations | Run ingest; check `/health` `methodology_vectors` |
| Qdrant connection refused | `docker compose up -d qdrant` |
| MCP tool empty memory | Use app chat first to create memories; check `user_id` |
| pytest DB errors | `$env:SKIP_DB_INIT="1"` |
| Port 8000 in use | Use `--port 8001` (documented default on Windows) |

---

## 9. Demo day checklist

- [ ] `backend/.env` keys valid (OpenAI + Anthropic)
- [ ] Backend health green
- [ ] Frontend CONNECTED on `/chat`
- [ ] `output/*.md` present OR accept lexical fallback
- [ ] Qdrant running if claiming vector RAG live
- [ ] Langfuse: 1–2 trace screenshots ready
- [ ] Safety eval: run once, know pass count (25/25)
- [ ] PDF opens: `docs/athletecore_defense_presentation.pdf`
- [ ] Do not commit `.env` or rotate keys if exposed

---

## 10. Quick reference

| Action | Command |
|--------|---------|
| Backend | `uvicorn app.main:app --reload --port 8001` |
| Frontend | `npm run dev` |
| Tests | `pytest tests/ -q` |
| Safety eval | `python -m app.evals.run_safety_eval` |
| MCP | `python -m mcp_server.server` |
| Ingest RAG | `python scripts/ingest_methodology_qdrant.py --recreate` |

More: [README.md](README.md) · [PRESENTATION_BRIEF.md](PRESENTATION_BRIEF.md)
