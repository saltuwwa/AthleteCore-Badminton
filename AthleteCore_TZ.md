# AthleteCore — Техническое задание

> **Версия:** v0.2 (после ревью и консультации с ментором)
> **Дедлайн:** 20 мая · **Demo Days:** 26–28 мая
> **Статус:** MVP в активной разработке (frontend ✅, backend в работе)
> **Стек выбран:** Python · FastAPI · LangGraph · Qdrant · React · LangSmith · LiteLLM

---

## 0. Легенда

В каждом разделе техрешения помечены:
- ✅ **ВЫБРАНО** — берём в MVP
- 🔄 **АЛЬТЕРНАТИВА** — рассматривали, отказались по причине ниже
- 💡 **ОБОСНОВАНИЕ** — почему именно так
- 🎯 **РИСК** — на что обратить внимание

---

## 1. Суть продукта

**AthleteCore** — AI-система управления карьерой для **профессиональной бадминтонистки**, совмещающей спорт с учёбой/работой. Не дневник — **система поддержки решений**.

**Ключевая боль:** информационный хаос. Матчевые данные, расписание, физическое состояние, тактические ошибки существуют в разных местах и не анализируются в связке.

**Что делает система:**
- Принимает голосовые/текстовые логи после тренировок и матчей
- Проводит **причинно-следственный анализ ошибок** (не «что было», а «почему повторяется»)
- Строит **оптимизированное недельное/дневные/месячные расписания** с учётом нагрузки и восстановления
- Даёт тактические рекомендации на основе **исторических паттернов**
- Подтягивает живой **BWF ранг** (скрейпинг) и связи с другими игроками

**Сценарий пользователя (happy path):**
1. После матча игрок нажимает 🎙 → говорит лог (1–3 мин)
2. Whisper транскрибирует → отправляется в LangGraph
3. Planner Agent маршрутизирует на Analyst → Schedule → Health Coach
4. Analyst достаёт из RAG похожие матчи, ищет повторы → отдаёт root cause + рекомендацию
5. Schedule Agent корректирует план недели через MCP
6. **Human checkpoint**: игрок видит «AI добавил X в расписание» → подтверждает
7. План закрепляется, лог индексируется в `user_history`

---

## 2. Архитектура: технологический стек

### Сводная таблица

| Слой | ✅ Выбрано | 🔄 Альтернатива | 💡 Обоснование |
|---|---|---|---|
| Оркестрация агентов | **LangGraph** | Strands Agents | Эталонный supervisor + HITL кейс. Визуализируется на защите. Нативный LangSmith. Большое community = меньше дебага в одиночку |
| Primary LLM | **Claude Sonnet 4.5** | Gemini 2.5 Pro | Лучший reasoning под root-cause анализ. Vision из коробки. $3/$15 за 1М tok |
| LLM fallback / cheap | **GPT-4o-mini** | Claude Haiku | В 10× дешевле, приемлемое качество для Planner-роутинга и форматирования |
| LLM gateway | **LiteLLM** | прямые SDK | Один интерфейс на все провайдеры + автоматический fallback + semantic cache одной строкой |
| Vector DB | **Qdrant (Docker)** | pgvector, Chroma | Мощные фильтры (нужны `user_id` + `event_type`), хорошая скорость, бесплатный self-host |
| Embeddings | **text-embedding-3-small** | Voyage-3, bge-m3 | Дёшево ($0.02/1M tok), качество достаточное для домена. Voyage-3 лучше, но дороже и vendor-lock |
| Reranker | **cross-encoder/ms-marco-MiniLM-L-6-v2** | без reranker | Маленькая модель, копеечный, реально улучшает Analyst — критично |
| STT | **Whisper-1 API** | Deepgram, whisper.cpp | Лучшее качество спортивного жаргона. $0.006/мин — копейки |
| Vision (опц.) | **Claude Vision** | GPT-4o vision | Лучше читает рукописные тактические схемы. Если останется время |
| MCP | **Custom MCP server** | обычные tool functions | На защите даёт сигнал «системное мышление». 3 тула за вечер |
| Backend | **FastAPI 0.115+ / Python 3.11** | — | Стандарт. Async. Pydantic. Авто-doc |
| Frontend | **React 19 + Vite + TS + Tailwind v4** | — | ✅ Уже реализован skeleton (см. `frontend/`) |
| База данных | **SQLite (MVP)** | PostgreSQL | Одна юзер-сессия для демо. Postgres переключим одной строкой если нужно |
| Мониторинг | **LangSmith** | Langfuse self-host | Идёт «в комплекте» с LangGraph. Бесплатно до 5K traces/мес |
| Error tracking | **Sentry** | Bugsnag | Бесплатный free tier. У нас уже есть установленный скилл `sentry` |
| Контейнеризация | **Docker + docker-compose** | — | Один `docker-compose up` для локального запуска |
| Deploy frontend | **Vercel** | Netlify, Cloudflare Pages | Бесплатно, deploy от git push, отлично с Vite |
| Deploy backend | **Render** | Railway, Fly.io | $7/мес, поддерживает Docker, persistent volumes для Qdrant |
| CI/CD | **GitHub Actions** | — | Прогон `run_evals.py` на каждый PR |

🎯 **Риск стека**: Qdrant в Docker на Render требует volume mount — заложить 30 мин на конфиг.

---

## 3. LangGraph: структура агентов

### Граф состояний

```
[User Input — text / voice / image]
     ↓
[Input Processor]   — STT через Whisper, Vision через Claude, парсинг текста
     ↓
[Planner Agent]     — SUPERVISOR: решает кого звать
     ↓ (conditional routing — может вызвать несколько)
     ├── [Analyst Agent]      — анализ матча, root cause ошибок, RAG-паттерны
     ├── [Schedule Agent]     — недельный план через MCP
     └── [Health Coach Agent] — нагрузка, восстановление, питание
          ↓
     [Aggregator Node]    — собирает ответы агентов
          ↓
     [Human Checkpoint]   — ⚠️ HITL: подтверждение плана
          ↓
     [Output Formatter]   — финальный ответ + индексация в user_history
```

Подробная Mermaid-диаграмма — в `ARCHITECTURE.md`.

### Агенты — гиперпараметры

| Агент | Модель | Temp | 💡 Почему |
|---|---|---|---|
| Planner (supervisor) | GPT-4o-mini | 0.1 | Маршрутизация → детерминированность. Дёшево, нет смысла платить Sonnet |
| Analyst | **Claude Sonnet 4.5** | 0.2 | Reasoning по паттернам — критично. Минимум галлюцинаций |
| Schedule | GPT-4o-mini | 0.3 | Tool calls в MCP, небольшая вариативность ок |
| Health Coach | Claude Sonnet 4.5 | 0.4 | Гибкость формулировок для рекомендаций |

✅ **ВЫБРАНО: multi-model routing**.
💡 Экономит ~60% бюджета и даёт более внятный ответ ментору на вопрос «почему именно эта модель»: «потому что задача-специфично».

### Промпт Analyst (v2 — chain-of-thought, после A/B)

```python
ANALYST_SYSTEM = """
You are a professional sports performance analyst for badminton.
Your job is NOT to describe what happened, but to identify WHY errors occur
and whether they form patterns.

THINK STEP BY STEP:
1. Read the user's match log.
2. Check the provided historical context (RAG output): has a similar error appeared before?
3. For each error identified, classify root cause category:
   - physical_fatigue / tactical_gap / psychological / technical
4. Assign recurrence risk: high / medium / low (high = ≥3 occurrences)
5. Suggest ONE concrete corrective action for the next training.

Be direct. No filler. Output structured JSON matching schema in tool description.
"""
```

### Промпт Planner (supervisor)

```python
PLANNER_SYSTEM = """
You are AthleteCore's routing supervisor. Analyze the user's input and decide:
1. Which specialist agents to invoke (can be multiple).
2. Priority and sequence of agent calls.
3. Whether human confirmation is needed before finalizing.

Agents:
- analyst: match analysis, tactical errors, performance patterns
- scheduler: calendar planning, weekly load distribution
- health_coach: recovery, nutrition, physical load

Default: route to analyst FIRST when input contains match/training performance data.
"""
```

---

## 4. RAG Pipeline

### Два индекса в Qdrant

**Index 1: `sports_methodology`** — статика
- Источники: PDF-учебники по бадминтону, спорт. методология, нутрициология
- Chunking: `RecursiveCharacterTextSplitter`, chunk_size=512, overlap=64
- Обновление: вручную при добавлении новых материалов

**Index 2: `user_history`** — динамика
- Источники: все логи матчей и тренировок пользователя
- Chunking: sentence-level (одно событие = один чанк)
- Обновление: после каждого нового лога (real-time)

### Retrieval стратегия

```python
def retrieve_for_analysis(query: str, user_id: str):
    # 1. Personal history (k=5, filter by user_id)
    personal = qdrant.search(
        collection="user_history",
        query_vector=embed(query),
        query_filter={"user_id": user_id},
        limit=5,
    )
    # 2. Methodology (k=3, no filter)
    methodology = qdrant.search(
        collection="sports_methodology",
        query_vector=embed(query),
        limit=3,
    )
    # 3. Rerank top-8 → top-5
    return rerank(personal + methodology, top_k=5)
```

✅ **ВЫБРАНО**: semantic + reranker.
🔄 **АЛЬТЕРНАТИВА**: hybrid (semantic + BM25) — даёт ещё +5–10% на edge cases, но усложняет stack (нужен Tantivy/OpenSearch). Отложили на v0.3.

---

## 5. MCP Server

### Файл: `mcp_server/athletecore_mcp.py`

```python
from mcp.server import Server

server = Server("athletecore")

@server.tool()
async def get_calendar_events(date_from: str, date_to: str, user_id: str) -> dict:
    """Get user's calendar events in date range."""
    ...

@server.tool()
async def create_training_block(
    title: str, date: str, duration_minutes: int,
    intensity: str,  # low/medium/high
    user_id: str,
) -> dict:
    """Create a training block in user's calendar."""
    ...

@server.tool()
async def get_performance_history(user_id: str, days_back: int = 30) -> dict:
    """Get user's performance logs for the last N days."""
    ...
```

💡 **Почему MCP, а не обычный API**: агенты могут вызывать тулы независимо от бэкенда. В будущем легко подключить Google Calendar / Outlook через один интерфейс без изменения агентского кода. На защите — сильный сигнал «архитектурное мышление».

---

## 6. Мультимодальность

### Voice logging (основной сценарий)
```
🎙 Record → AudioBlob → POST /api/transcribe (Whisper) → текст → стандартный pipeline
```

💡 **Почему важно**: голос — единственный реалистичный способ логировать после матча. Спортсмен уставший, печатать неудобно.

### Vision (опционально, если останется время)
```
📷 Photo схемы → Claude Vision → structured description → контекст для Analyst
```

🎯 **Решение по таймингу**: Vision реализуем **последним**. Если за неделю до Demo Days не будет — фокус на RAG и evals.

---

## 7. Мониторинг и оценка

### LangSmith Setup
```python
import os
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = "..."
os.environ["LANGCHAIN_PROJECT"] = "athletecore-prod"
```

Каждый вызов агента трейсится автоматически. На защите показать dashboard с реальным сценарием.

### Golden Dataset (40 примеров — увеличили с 30)

Структура:
```json
{
  "input": "голосовой лог после матча (транскрипт)",
  "expected_error_categories": ["tactical", "physical"],
  "expected_has_pattern": true,
  "expected_recommendation_quality": "specific",
  "reference_answer": "эталонный анализ"
}
```

💡 40 примеров вместо 30: 30 типовых + 10 edge cases (короткие логи, без ошибок, противоречивые данные).

### Метрики (автоматизированный прогон)

**Метрика 1: Relevance** (LLM-as-judge, GPT-4o)
```python
JUDGE_PROMPT = """
Rate tactical advice relevance on a 1-5 scale.
User log: {input}
System advice: {output}
Rate ONLY relevance to the specific situation. Output ONLY a number 1-5.
"""
```

**Метрика 2: Pattern Detection Accuracy**
- Binary: обнаружил ли агент повторяющийся паттерн, если он есть в golden dataset.
- Считается через JSON-парсинг ответа.

**Метрика 3: Latency p50/p95**
- Время от запроса до полного ответа graph.

**Метрика 4: Cost per query**
- Из LangSmith → average tokens × pricing.

### A/B Эксперимент

**Гипотеза:** Analyst с chain-of-thought промптом (v2) точнее определяет root cause, чем direct (v1).

```python
CONFIGS = {
    "v1_direct": {"temperature": 0.3, "prompt": ANALYST_V1},
    "v2_cot":    {"temperature": 0.2, "prompt": ANALYST_V2_COT},
}
```

Прогон на golden dataset → сравнение relevance score + pattern accuracy.
**Ожидание:** v2 даёт +0.4–0.6 по relevance, +10–15% pattern accuracy.

---

## 8. Custom Skill

### Файл: `skills/athletic_analysis/SKILL.md`

```markdown
---
name: athletic-performance-analysis
description: Specialized skill for analyzing badminton athlete performance logs,
identifying recurring tactical/physical errors via RAG over personal history.
triggers:
  - "проанализируй матч"
  - "разбор тренировки"
  - "что я делаю не так"
  - "performance review"
  - "training feedback"
---
```

---

## 9. Структура проекта

```
athletecore/
├── backend/
│   ├── agents/
│   │   ├── planner.py            # LangGraph supervisor
│   │   ├── analyst.py            # Performance analysis agent
│   │   ├── scheduler.py          # Schedule building agent
│   │   └── health_coach.py       # Health/nutrition agent
│   ├── graph/
│   │   └── workflow.py           # LangGraph StateGraph definition
│   ├── rag/
│   │   ├── indexer.py            # Document ingestion + chunking
│   │   ├── retriever.py          # Hybrid retrieval logic
│   │   ├── reranker.py           # Cross-encoder rerank
│   │   └── embeddings.py         # Embedding wrapper
│   ├── mcp_server/
│   │   └── athletecore_mcp.py    # Custom MCP server
│   ├── llm/
│   │   └── gateway.py            # LiteLLM router + fallback + cache
│   ├── api/
│   │   ├── main.py               # FastAPI app
│   │   ├── routes/
│   │   │   ├── chat.py           # Main chat endpoint
│   │   │   ├── transcribe.py     # Whisper STT endpoint
│   │   │   ├── schedule.py       # Schedule CRUD
│   │   │   ├── history.py        # User history endpoints
│   │   │   └── bwf.py            # BWF rank scraping (cached 24h)
│   │   └── models.py             # Pydantic schemas
│   ├── evals/
│   │   ├── golden_dataset.json   # 40 test cases
│   │   ├── run_evals.py          # Automated evaluation script
│   │   └── ab_test.py            # A/B testing runner
│   └── skills/
│       └── athletic_analysis/
│           └── SKILL.md
├── frontend/                      # ✅ React + Vite + TS + Tailwind (готов skeleton)
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   └── App.tsx
│   └── package.json
├── docker-compose.yml
├── README.md
├── ARCHITECTURE.md                # ← Mermaid диаграммы
├── EVALS.md
└── AthleteCore_TZ.md              # ← этот файл
```

---

## 10. API Endpoints

```
POST   /api/chat              — основной чат (text + optional image)
POST   /api/transcribe        — аудио → текст (Whisper)
GET    /api/history?limit=20  — история логов пользователя
POST   /api/log               — сохранить лог напрямую
GET    /api/schedule?week=    — текущее расписание
POST   /api/schedule          — создать событие
POST   /api/schedule/:id/confirm — HITL подтверждение AI-плана
POST   /api/feedback          — оценка пользователем ответа
GET    /api/bwf?name=         — BWF ранг (скрейпинг + 24h cache)
GET    /api/health            — healthcheck (для Render)
```

---

## 11. Docker Setup

```yaml
# docker-compose.yml
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      - ANTHROPIC_API_KEY
      - OPENAI_API_KEY
      - LANGCHAIN_API_KEY
      - SENTRY_DSN
    depends_on: [qdrant]
    volumes:
      - ./data:/app/data    # SQLite + uploaded files

  frontend:
    build: ./frontend
    ports: ["5173:5173"]

  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333"]
    volumes: ["./qdrant_data:/qdrant/storage"]
```

**Запуск:** `docker-compose up --build`

---

## 12. Чек-лист допуска к защите

### Must have (без этого не допускают)

- [ ] MCP сервер с 3 тулами (`get_calendar_events`, `create_training_block`, `get_performance_history`)
- [ ] `SKILL.md` для athletic_analysis
- [ ] LangGraph StateGraph с ветвлением + HITL checkpoint
- [ ] RAG pipeline: 2 индекса в Qdrant, обоснованный chunking, reranker
- [ ] Обработка документов (PDF парсинг методологии для индекса)
- [ ] Мультимодальность: Whisper STT (must) + Claude Vision (nice-to-have)
- [ ] LangSmith логирование всех вызовов
- [ ] Golden dataset 40 примеров + автоматический прогон evals
- [ ] A/B эксперимент Analyst v1 vs v2 с выводами и графиком
- [ ] Обоснование выбора LLM + гиперпараметров (этот файл закрывает)
- [ ] React фронтенд (не CLI) — ✅ уже есть
- [ ] README.md + ARCHITECTURE.md + EVALS.md
- [ ] Презентация 10–15 слайдов

### Nice to have (бонусные баллы)

- [ ] **LiteLLM gateway** с fallback Sonnet → GPT-4o-mini
- [ ] **Semantic cache** (через LiteLLM) — снижает стоимость повторов
- [ ] **Sentry** для error tracking в проде
- [ ] **Playwright** smoke-тесты (логин, голос, подтверждение плана)
- [ ] **Деплой** на Vercel + Render (публичный URL для демо)
- [ ] **CI/CD**: GitHub Actions запускает `run_evals.py` на каждый PR в main
- [ ] **Security review** через скилл `security-best-practices`
- [ ] **Threat model** через скилл `security-threat-model`

---

## 13. Бюджет токенов и стоимость

**Сценарий**: 1 матч-лог → весь pipeline.

| Этап | Tokens in | Tokens out | Модель | $ |
|---|---|---|---|---|
| STT (Whisper) | — | — | whisper-1 | $0.018 (3 мин) |
| Planner | 600 | 80 | gpt-4o-mini | $0.0001 |
| Retrieval | (внутр.) | — | embedding-3-small | $0.00001 |
| Analyst | 2200 | 500 | sonnet-4.5 | $0.0142 |
| Schedule | 1000 | 250 | gpt-4o-mini | $0.0003 |
| Health Coach | 900 | 200 | sonnet-4.5 | $0.0057 |
| Aggregator | 800 | 200 | gpt-4o-mini | $0.0002 |
| **Итого / запрос** | | | | **~$0.038** |

💡 На 100 матч-логов = ~$4. На демо-неделю с 200 прогонами evals ≈ $30.

---

## 14. Безопасность

Прогнать через установленные скиллы перед защитой:
- `security-best-practices` — поиск утечек ключей, SQL injection, prompt injection
- `security-threat-model` — формальный threat model: trust boundaries, attacker capabilities
- `security-ownership-map` — карта владения чувствительным кодом

🎯 **Ключевые точки риска**:
1. API ключи (Anthropic / OpenAI / LangSmith) → `.env` + Render secrets, никогда не в git
2. Prompt injection в голосовых логах → strip control tokens, ограничить tool calls
3. User data в RAG → фильтр по `user_id` обязателен на каждом retrieval
4. CORS на FastAPI → только origin фронта
5. Rate limiting на `/api/chat` (через slowapi) — защита от заливания

---

## 15. План работ до защиты

### Неделя 1 (текущая) — backend skeleton
- [x] Frontend skeleton (готов)
- [ ] FastAPI + LiteLLM gateway
- [ ] LangGraph StateGraph с 4 нодами (без RAG ещё)
- [ ] Qdrant локально + 2 индекса
- [ ] Whisper endpoint

### Неделя 2 — RAG + MCP
- [ ] RAG pipeline + reranker
- [ ] MCP server с 3 тулами
- [ ] HITL checkpoint
- [ ] Golden dataset (первые 20 кейсов)

### Неделя 3 — evals + polish
- [ ] Доделать golden dataset до 40
- [ ] A/B эксперимент
- [ ] LangSmith dashboard
- [ ] Sentry + CI
- [ ] Деплой Vercel + Render

### Неделя 4 — Demo Days
- [ ] Презентация
- [ ] Видео-демо (90 сек)
- [ ] Финальный security pass
- [ ] Vision (если время)

---

## 16. Открытые вопросы к ментору

1. **Vector DB**: оставляем Qdrant или переключаем на pgvector ради одной БД?
2. **Vision**: брать ли в MVP или фокус на RAG + evals?
3. **Golden dataset**: 40 достаточно или нужно 60+?
4. **A/B**: одного эксперимента (Analyst v1 vs v2) хватит или добавить второй (embedding A/B)?
5. **Deploy**: Vercel + Render vs single Docker-compose на VPS — что менее рисково?
6. **Domain filter (guardrails)**: проверка «вопрос действительно про спорт» — нужно или не нужно?

---

*AthleteCore v0.2 — MVP для курса LLM Engineer*
