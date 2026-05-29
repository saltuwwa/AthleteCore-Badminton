# AthleteCore — Defense Presentation (source)

Editable source for `athletecore_defense_presentation.pdf`.  
Regenerate PDF: `python scripts/generate_defense_pdf.py`

---

## Slide 1 — Title

**AthleteCore** — AI sports memory & coaching assistant for badminton athletes.

Hook: Не просто чат-бот, а система памяти, анализа и grounded coaching для спортсмена.

**Speaker notes:** Представь продукт как LLM Engineer final project. Персона — профессиональная бадминтонистка Айгерим (course MVP, не production B2B).

---

## Slide 2 — Problem

- Тренировки, матчи, усталость теряются между сессиями
- Chatbot не помнит историю
- LLM может выдумать прошлую тренировку
- Нужен честный анализ на реальных данных

**Speaker notes:** Приведи контраст: generic «отдыхай» vs персональный план только при наличии LTM.

---

## Slide 3 — Solution

Voice/text logs · LTM · LangGraph · RAG · MCP · evals + Langfuse

**Speaker notes:** Это не список buzzwords — каждый блок имеет код в репозитории (README, ARCHITECTURE).

---

## Slide 4 — End-to-end scenario

Flow: voice/text → Whisper → draft → /api/chat → router → memory/RAG/agents → response

Example: «Сегодня тренировка: смэши, усталость, подача лучше»

**Speaker notes:** Покажи live в /chat если есть время. Подчеркни background memory write.

---

## Slide 5 — Where data goes

Memory ≠ RAG. Memory = athlete history (SQLite). RAG = methodology (Qdrant). Agents = decisions. MCP = tools.

**Speaker notes:** Самый важный conceptual slide для менторов.

---

## Slide 6 — Architecture mindmap

Frontend · FastAPI · LangGraph · SQLite · Qdrant · Whisper · MCP · Skill · Langfuse · Evals · Video MVP

**Speaker notes:** Video MVP — partial, не core demo path.

---

## Slide 7 — LangGraph

planner → load_memory? → analyst | health_coach | scheduler | direct → aggregator

**Speaker notes:** Conditional memory — cost + precision. Checkpointer для thread continuity.

---

## Slide 8 — Memory

event_date, facts JSON, write-gate, background extraction, past-event guard.  
Example: 29 мая «вчера тренировка» → event_date 28 мая.

**Speaker notes:** Date normalization в коде, не LLM freeform.

---

## Slide 9 — Anti-hallucination

«Разбери 10 февраля» → check memory → found / not_found (llm_called=false)

**The system does not hallucinate missing training logs.**

**Speaker notes:** Demo Scenario 2 на защите — must show. pytest test_api_chat_past_event.

---

## Slide 10 — RAG

PDF → output/*.md → chunk → embeddings → Qdrant → context → answer

**Speaker notes:** output/*.md локально после LlamaParse — не в git. Lexical fallback если Qdrant down.

---

## Slide 11 — MCP

4 tools: recall_athlete_memory, search_sports_methodology, get_training_schedule, propose_training_block

**Speaker notes:** propose = pending_confirmation HITL. MCP для Cursor; chat использует тот же mcp_tools in-process.

---

## Slide 12 — Custom Skill

`.agents/skills/athletecore/SKILL.md` — triggers, analyst workflow, memory gate, MCP rules

**Speaker notes:** Skill лучше generic prompt — stable paths + domain guardrails.

---

## Slide 13 — Evals + Observability

25 safety · ~195 pytest · Langfuse (not LangSmith) · no production A/B

**Speaker notes:** Честно: offline safety eval + regression, не user A/B.

---

## Slide 14 — Status

Implemented vs Partial/Missing — History mock, auth missing, formal Analyst A/B missing

**Speaker notes:** Chat live; /history seed data — не путать с server LTM.

---

## Slide 15 — Closing

Roadmap + final line: memory-driven, grounded AI coaching system.

**Speaker notes:** Спасибо, Q&A. Не claim production users.

---

## Honest claims checklist

| Claim | OK? |
|-------|-----|
| LangGraph + conditional memory | ✅ |
| past_event not_found | ✅ |
| 25 safety / ~195 pytest | ✅ |
| Langfuse tracing | ✅ (if enabled) |
| Production users | ❌ do not say |
| Production A/B | ❌ do not say |
| LangSmith in code | ❌ do not say |
| History UI = live memory browser | ❌ mock only |
| BWF scraping | ❌ not implemented |
