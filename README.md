# AthleteCore

AI-система карьерного менеджмента для **профессиональной бадминтонистки** (персона Айгерим): анализ матчей и тренировок, долгосрочная память, методология из coaching-книг, расписание с human-in-the-loop.

Финальный проект курса **LLM Engineer**. Репозиторий: [github.com/saltuwwa/AthleteCore-Badminton](https://github.com/saltuwwa/AthleteCore-Badminton)

---

## Возможности

| Модуль | Описание |
|--------|----------|
| **Чат + голос** | Whisper STT → черновик → ручная отправка → LangGraph pipeline |
| **LangGraph** | Planner → (LTM recall) → Analyst / Health Coach / Scheduler / Direct → Aggregator |
| **LTM** | Структурированная память в SQLite, hybrid recall, memory gate, write-gate |
| **Методология** | Поиск по распарсенным PDF (`output/*.md`), lexical MVP (Qdrant — в плане) |
| **Расписание** | SQLite-календарь, AI-предложения со статусом `pending_confirmation` |
| **MCP** | Собственный stdio-сервер с 4 domain tools для Cursor |
| **Skill** | `.agents/skills/athletecore/SKILL.md` — домен, триггеры, workflows |

---

## Стек

- **Frontend:** React 19, Vite, TypeScript, Tailwind CSS v4
- **Backend:** FastAPI, LangGraph, LiteLLM (OpenAI + Anthropic), SQLite
- **STT:** OpenAI Whisper
- **Парсинг PDF:** LlamaParse (`scripts/parse_badminton_pdf.py`)

---

## Структура репозитория

```
.
├── backend/              # FastAPI, LangGraph, memory, schedule
├── frontend/             # React SPA
├── mcp_server/           # MCP stdio server (athletecore)
├── scripts/              # PDF → Markdown
├── .agents/skills/athletecore/   # Course Skill (SKILL.md)
├── .cursor/mcp.json      # Cursor MCP config
├── output/               # Parsed books (локально, не в git)
├── book sources/         # Исходные PDF (локально, не в git)
├── ARCHITECTURE.md
├── MEMORY_ARCHITECTURE.md
└── AthleteCore_TZ.md
```

---

## Требования

- **Python 3.11+**
- **Node.js 18+** (для frontend)
- Ключи API (см. ниже)

| Ключ | Назначение |
|------|------------|
| `OPENAI_API_KEY` | Whisper, Planner, embeddings, часть нод |
| `ANTHROPIC_API_KEY` | Analyst (Claude Sonnet) — желательно |
| `LLAMA_CLOUD_API_KEY` | Только для парсинга PDF |
| `GOOGLE_API_KEY` | Опционально: multimodal parse (Gemini) |

---

## Быстрый старт (Windows)

### 1. Клонирование и venv

```powershell
git clone https://github.com/saltuwwa/AthleteCore-Badminton.git
cd AthleteCore-Badminton

python -m venv venv
.\venv\Scripts\Activate.ps1
```

> Все Python-зависимости ставьте **только в `venv`**, с активным `(venv)` в терминале.

### 2. Backend

```powershell
cd backend
copy .env.example .env
# Заполните OPENAI_API_KEY и ANTHROPIC_API_KEY в .env

python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8001
```

Проверка: http://127.0.0.1:8001/health  
Документация API: http://127.0.0.1:8001/docs

На Windows порт **8000** часто занят — используем **8001**.

### 3. Frontend (второй терминал)

```powershell
cd frontend
copy .env.example .env
# VITE_API_PROXY_TARGET=http://127.0.0.1:8001

npm install
npm run dev
```

Откройте http://localhost:5173 → **Главная** (`/home`) или **Чат** (`/chat`).

### 4. Альтернатива: pip без активации venv

```powershell
cd backend
..\venv\Scripts\python.exe -m pip install -r requirements.txt
..\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
```

---

## Переменные окружения

**Backend** — `backend/.env` (шаблон: `backend/.env.example`):

```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-...
DATABASE_URL=sqlite+aiosqlite:///./athletecore.db
GRAPH_CHECKPOINT_PATH=./graph_checkpoints.sqlite
PLANNER_MODEL=gpt-4o-mini
ANALYST_MODEL=claude-sonnet-4-20250514
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
DISABLE_RERANKER=1
```

**Frontend** — `frontend/.env`:

```env
VITE_API_PROXY_TARGET=http://127.0.0.1:8001
```

Файлы `.env` **не коммитятся** (см. `.gitignore`).

---

## Методология (PDF → RAG)

Исходники PDF храните локально в `book sources/`. Результат парсинга — в `output/*.md` (тоже локально, не в git).

```powershell
.\venv\Scripts\Activate.ps1
cd scripts
pip install -r requirements-parse.txt

# Пример: footwork ebook
python parse_badminton_pdf.py --pdf "..\book sources\Badminton-Footwork-Pocket-eBook_compressed-V2.pdf"
```

Подробнее: `scripts/parsing_instruction.txt`, skill reference `.agents/skills/athletecore/references/rag-ingest.md`.

Без `output/*.md` Analyst всё равно работает, но без цитат из coaching-книг.

### Qdrant RAG (векторный поиск)

```powershell
# 1) Qdrant
docker compose up -d qdrant

# 2) Зависимости backend (если ещё не ставили)
cd backend
..\venv\Scripts\pip install -r requirements.txt

# 3) Ingest всех output/*.md → коллекция sports_methodology
cd ..
..\venv\Scripts\python scripts\ingest_methodology_qdrant.py --recreate
```

Проверка: http://127.0.0.1:8001/health → `"methodology_rag": "qdrant"`, `methodology_vectors` > 0.

**Chunking:** по маркерам `<!-- page N -->`, крупные страницы режутся ~900 токенов (overlap 120).  
**Embeddings:** `text-embedding-3-small` (1536d).  
**Retrieval:** cosine в Qdrant; опционально cross-encoder rerank (`DISABLE_RERANKER=0`).  
**Fallback:** если Qdrant выключен — lexical поиск по `output/*.md`.

---

## MCP Server (курс)

Собственный MCP для Cursor / Claude Desktop:

| Tool | Назначение |
|------|------------|
| `recall_athlete_memory` | LTM hybrid recall |
| `search_sports_methodology` | Поиск по `output/*.md` |
| `get_training_schedule` | Календарь |
| `propose_training_block` | Черновик события (HITL) |

**Запуск вручную** (из корня проекта):

```powershell
$env:PYTHONPATH="backend"
.\venv\Scripts\python.exe -m mcp_server.server
```

**Cursor:** `.cursor/mcp.json` → перезапуск Cursor → Settings → MCP → включить **athletecore**.

Детали: [mcp_server/README.md](mcp_server/README.md)

---

## Skill (курс)

Проектный skill: [.agents/skills/athletecore/SKILL.md](.agents/skills/athletecore/SKILL.md)  
Триггеры: badminton, AthleteCore, Analyst, матч, footwork, memory gate, Demo Days.

---

## Основные API

| Endpoint | Описание |
|----------|----------|
| `GET /health` | Статус backend |
| `POST /api/chat` | Чат (LangGraph) |
| `POST /api/transcribe` | Голос → текст (Whisper) |
| `GET /api/schedule/events` | Календарь |
| `POST /recall`, `POST /search` | Memory API |

---

## Тесты (backend)

```powershell
cd backend
$env:SKIP_DB_INIT="1"
..\venv\Scripts\python.exe -m pytest tests/ -q
```

---

## Документация

| Файл | Содержание |
|------|------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Диаграммы, поток запроса |
| [MEMORY_ARCHITECTURE.md](MEMORY_ARCHITECTURE.md) | LTM/STM, recall, write-gate |
| [AthleteCore_TZ.md](AthleteCore_TZ.md) | ТЗ, модели, чек-лист защиты |
| [backend/README.md](backend/README.md) | Memory research, API |
| [frontend/README.md](frontend/README.md) | Frontend |

---

## Демо-сценарий (60–90 сек)

1. Запустить backend + frontend.
2. Открыть **Чат**, проверить статус **CONNECTED**.
3. Записать голосовой лог матча → проверить черновик → отправить.
4. Получить ответ **Analyst** (карточка анализа + текст).
5. (Опционально) запрос на план тренировки → Scheduler → `pending_confirmation` в календаре.

---

## Roadmap (финальный проект курса)

- [x] Qdrant RAG `sports_methodology` (+ lexical fallback)
- [ ] LangSmith трейсинг
- [ ] Golden dataset + `EVALS.md` + A/B Analyst
- [ ] HITL UI на Schedule (confirm/reject)
- [ ] Презентация Demo Days

---

## Лицензия и автор

Учебный финальный проект. Код и документация — для защиты на курсе LLM Engineer.
