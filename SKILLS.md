# AthleteCore — Custom Skill

## 1. What custom skill exists

**athletecore** — domain skill for badminton athlete AI development and agent behavior in Cursor.

---

## 2. Location of SKILL.md

```
.agents/skills/athletecore/
├── SKILL.md                    # Main skill (frontmatter + workflows)
└── references/
    ├── analyst-workflow.md
    ├── memory-gate.md
    ├── mcp-tools.md
    └── rag-ingest.md
```

---

## 3. Skill triggers

From YAML frontmatter (`description` field):

- badminton, AthleteCore, Analyst, спортсменка, матч, подача, footwork
- memory gate, LlamaParse, Qdrant RAG, Demo Days
- LangGraph agents: Planner, Health Coach, Scheduler
- MCP tool names

Cursor loads skills when user or task matches these concepts.

---

## 4. Skill instructions (summary)

| Area | Instruction |
|------|-------------|
| **Product** | Career management for pro badminton — not generic chat |
| **Architecture map** | Points to `backend/app/graph`, `memory`, `mcp_tools`, frontend |
| **MCP** | When to call each of 4 tools; do not recall memory for off-topic |
| **Analyst** | Error taxonomy, JSON `errors[]` fence, methodology search |
| **Scheduler** | `get_training_schedule` first; `PROPOSE:` line format; HITL |
| **Memory gate** | `needs_memory` true/false rules |
| **RAG ingest** | PDF → `output/*.md` → Qdrant ingest script |

---

## 5. When skill is activated

- Developer works on AthleteCore repo in Cursor with skills enabled.
- User message mentions badminton domain, memory, Analyst, or course demo.
- Compatible with **athletecore** MCP server (`compatibility` note in SKILL.md).

---

## 6. Why skill beats a generic prompt

| Generic prompt | AthleteCore skill |
|----------------|-------------------|
| Forget repo layout | Stable paths to graph, memory, MCP |
| Guess tool usage | Explicit MCP decision table |
| Mix medical advice | Domain boundaries in analyst workflow |
| Skip HITL | Scheduler must use `pending_confirmation` |
| Old RAG state | References updated for Qdrant ingest |

---

## 7. Example input / output

**Input (developer):**  
*«Add past-event guard test for match comparison»*

**Skill-guided behavior:**  
Open `backend/app/memory/past_event_guard.py`, `tests/test_target_resolution.py`, follow analyst-workflow reference; do not break semantic-router invariants.

**Input (agent with MCP):**  
*«Drill for split-step latency»*

**Expected:** `search_sports_methodology` → cite `source` filename; optional `recall_athlete_memory` if user history relevant.

---

## 8. Badminton-specific value

- Terminology: match, footwork, serve, recovery blocks.
- Methodology corpus from real coaching PDFs (not LLM imagination).
- Schedule types aligned with athlete calendar (MATCH, TRAINING, RECOVERY).
- Risk patterns (recurring errors ≥3) documented in analyst reference.

---

## 9. Improvements

- [ ] Align SKILL “future Qdrant” wording — **Qdrant is implemented** (update reference in `rag-ingest.md` if needed).
- [ ] Add defense-day checklist section to SKILL.md.
- [ ] Version bump when Analyst prompt v2 ships.
- [ ] Link to [EVALS.md](EVALS.md) and [OBSERVABILITY.md](OBSERVABILITY.md).

---

## Standard compliance

Skill uses Cursor skill frontmatter:

```yaml
---
name: athletecore
description: "..."
license: MIT
compatibility: Works with AthleteCore MCP server...
metadata:
  author: athletecore-team
  version: "1.0"
---
```

Matches course requirement for **SKILL.md** with triggers and instructions.
