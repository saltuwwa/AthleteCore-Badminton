# AthleteCore MCP Server

stdio MCP server exposing AthleteCore domain tools to Cursor / Claude Desktop / other MCP clients.

## Tools

| Tool | Purpose |
|------|---------|
| `recall_athlete_memory` | Hybrid LTM recall (same as `/recall`) |
| `search_sports_methodology` | Search `output/*.md` coaching books |
| `get_training_schedule` | SQLite calendar (seeded demo + pending AI blocks) |
| `propose_training_block` | HITL draft event (`pending_confirmation`) |

## Setup

```bash
cd backend
pip install -r requirements.txt
# OPENAI_API_KEY + LLAMA_CLOUD not required for schedule/methodology search
# OPENAI_API_KEY required for recall_athlete_memory
```

## Run manually

```bash
# From project root
set PYTHONPATH=backend
python -m mcp_server.server
```

## Cursor

`.cursor/mcp.json` is preconfigured. Restart Cursor → Settings → MCP → enable **athletecore**.

## LangGraph integration

Same functions in `backend/app/mcp_tools/`:

- **Analyst** auto-injects `search_sports_methodology` into context
- **Scheduler** auto-injects calendar + optional `PROPOSE:` line → `propose_training_block`
