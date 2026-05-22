# MCP tools reference

Server: `mcp_server/server.py`  
Shared logic: `backend/app/mcp_tools/`

## recall_athlete_memory

- `query` (required) — natural language
- `user_id` — default `aigerim`
- `session_id` — default `main`
- `max_tokens` — default 900

Returns `context` + `citations[]`.

## search_sports_methodology

- `query` — footwork, serve, drill name
- `top_k` — default 5, max 10

Searches `output/*.md` (LlamaParse). Returns `hits[].source`, `snippet`, `score`.

## get_training_schedule

- `date_from`, `date_to` — `YYYY-MM-DD` (default: today → +14d)
- `include_pending` — include `pending_confirmation` blocks

## propose_training_block

- `title`, `event_date`, `start_time`, `end_time` (required)
- `event_type` — TRAINING, RECOVERY, MATCH, STUDY, GYM
- `intensity` — 1–5

Creates **pending** event — never tell user it is final until confirmed.

## Example (schedule)

```
get_training_schedule(date_from="2026-05-20", date_to="2026-05-27")
→ see MATCH on 22nd
propose_training_block(title="Лёгкое восстановление", event_date="2026-05-23", start_time="10:00", end_time="11:00", event_type="RECOVERY", intensity=1)
```
