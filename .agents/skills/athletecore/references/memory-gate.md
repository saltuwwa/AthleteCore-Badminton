# Memory gate

Implemented in `backend/app/graph/memory_gate.py`.

## Load LTM (`needs_memory=true`)

- Match/training analysis, error patterns
- "Again", "same as last time", opponent-specific history
- Weekly plan with load, injuries, preferences
- Personalized recovery advice

## Skip LTM (`needs_memory=false`)

- Weather, news, small talk
- Single calendar CRUD ("move training to 18:00") without re-planning week
- Generic badminton rules without personal context

## MCP `recall_athlete_memory`

Same pipeline as graph `load_memory_node`. Use when coding/debugging memory quality.

Requires `OPENAI_API_KEY` for embeddings.
