# AthleteCore — Архитектура

> Сопроводительный документ к `AthleteCore_TZ.md`.
> Все диаграммы — в Mermaid, рендерятся в GitHub, Notion, VS Code Markdown Preview.

---

## 1. Карта системы (high-level)

```mermaid
flowchart LR
    subgraph Client["Client · Browser"]
        UI["React 19 SPA<br/>Vite · Tailwind v4 · Framer Motion"]
    end

    subgraph Edge["Edge / Hosting"]
        Vercel["Vercel · static SPA"]
    end

    subgraph Backend["Backend · Render"]
        API["FastAPI · async"]
        Gateway["LiteLLM Gateway<br/>routing · fallback · cache"]
        Graph["LangGraph StateGraph"]
        MCP["MCP Server<br/>3 tools"]
    end

    subgraph Data["Data Layer"]
        Qdrant[("Qdrant<br/>user_history<br/>sports_methodology")]
        SQLite[("SQLite<br/>users · schedules · logs")]
        Files[("Files · audio · pdfs")]
    end

    subgraph External["External APIs"]
        Anthropic["Anthropic<br/>Claude Sonnet 4.5"]
        OpenAI["OpenAI<br/>GPT-4o-mini · Whisper · embeddings"]
        BWF["bwfbadminton.com<br/>scraping"]
    end

    subgraph Observability
        LangSmith["LangSmith<br/>traces · evals"]
        Sentry["Sentry<br/>error tracking"]
    end

    UI -->|HTTPS| Vercel
    Vercel -->|API calls| API
    API --> Graph
    API --> MCP
    Graph --> Gateway
    Gateway --> Anthropic
    Gateway --> OpenAI
    Graph --> Qdrant
    MCP --> SQLite
    API --> Files
    API -->|cron 24h| BWF
    Graph -.->|trace| LangSmith
    API -.->|errors| Sentry
```

---

## 2. Поток агентов (LangGraph StateGraph)

```mermaid
flowchart TD
    Start([User input]) --> Input
    Input["Input Processor<br/>STT · Vision · text parse"] --> Planner

    Planner{{"Planner Agent<br/>SUPERVISOR<br/>model: gpt-4o-mini · t=0.1"}}

    Planner -->|"contains match data"| Analyst
    Planner -->|"asks about schedule"| Scheduler
    Planner -->|"asks about health"| Health
    Planner -->|"general question"| Direct

    Analyst["Analyst Agent<br/>Sonnet 4.5 · t=0.2<br/>RAG + reranker"]
    Scheduler["Schedule Agent<br/>gpt-4o-mini · t=0.3<br/>MCP tools"]
    Health["Health Coach Agent<br/>Sonnet 4.5 · t=0.4"]
    Direct["Direct Answer<br/>gpt-4o-mini"]

    Analyst --> Agg
    Scheduler --> Agg
    Health --> Agg
    Direct --> Agg

    Agg["Aggregator Node<br/>merge results"]
    Agg --> Check{"Needs human<br/>confirmation?"}

    Check -->|"yes (schedule changes)"| HITL
    Check -->|"no"| Format

    HITL[["HUMAN CHECKPOINT<br/>interrupt_before"]]
    HITL -->|"approved"| Format
    HITL -->|"rejected"| Planner

    Format["Output Formatter<br/>JSON → UI markdown"]
    Format --> Index["Index to user_history<br/>(Qdrant)"]
    Index --> End([Response to user])

    classDef supervisor fill:#7c6bff,color:#fff,stroke:#5a4bff
    classDef specialist fill:#161a24,color:#e8e4f0,stroke:#7c6bff
    classDef hitl fill:#ff6b8a,color:#fff,stroke:#cc4f6a
    classDef terminal fill:#b8ff6b,color:#000,stroke:#9bdc52

    class Planner supervisor
    class Analyst,Scheduler,Health,Direct specialist
    class HITL hitl
    class End terminal
```

---

## 3. RAG Pipeline (retrieval)

```mermaid
flowchart LR
    Q["User query<br/>(match log)"] --> Embed
    Embed["OpenAI<br/>text-embedding-3-small"]

    Embed --> Hist
    Embed --> Meth

    subgraph Search["Parallel search"]
        Hist["Qdrant search<br/>collection: user_history<br/>filter: user_id<br/>k=5"]
        Meth["Qdrant search<br/>collection: sports_methodology<br/>k=3"]
    end

    Hist --> Merge
    Meth --> Merge

    Merge["Concat top-8<br/>candidates"] --> Rerank
    Rerank["Cross-encoder<br/>ms-marco-MiniLM-L-6-v2"] --> Top5
    Top5["Top-5 chunks<br/>+ relevance score"] --> Ctx["Context to Analyst"]

    classDef vec fill:#161a24,color:#e8e4f0,stroke:#7c6bff
    classDef proc fill:#1d2230,color:#b8ff6b,stroke:#b8ff6b
    class Hist,Meth vec
    class Rerank,Merge proc
```

---

## 4. Voice logging (multimodal)

```mermaid
sequenceDiagram
    actor User as Athlete
    participant FE as Frontend
    participant API as FastAPI
    participant W as Whisper API
    participant Graph as LangGraph
    participant Q as Qdrant

    User->>FE: Tap 🎙 record
    FE->>FE: MediaRecorder (webm)
    User->>FE: Tap stop
    FE->>API: POST /api/transcribe (FormData)
    API->>W: audio file
    W-->>API: transcript text
    API-->>FE: { text }
    FE->>FE: Insert into input bar
    User->>FE: Edit if needed, press Send
    FE->>API: POST /api/chat { message }
    API->>Graph: invoke(graph_input)
    Graph->>Q: retrieve (user_history)
    Q-->>Graph: top-5 chunks
    Graph->>Graph: analyst + scheduler + health
    Graph-->>API: aggregated response
    API->>Q: index new log
    API-->>FE: response + analysis
    FE->>User: Render Message + AnalysisCard
```

---

## 5. Human-in-the-loop checkpoint

```mermaid
sequenceDiagram
    participant Graph as LangGraph
    participant API
    participant FE as Frontend
    actor User

    Graph->>Graph: Aggregator produces draft plan
    Graph->>Graph: interrupt_before: human_checkpoint
    Graph-->>API: state = AWAITING_CONFIRMATION<br/>+ proposed_changes
    API-->>FE: SSE event { type: "needs_confirmation", changes }
    FE->>User: Highlight AI-added schedule items
    User->>FE: Click ✓ Confirm Plan
    FE->>API: POST /api/schedule/{id}/confirm
    API->>Graph: resume(state, { approved: true })
    Graph->>Graph: continue execution
    Graph-->>API: final state
    API-->>FE: confirmation + persisted plan
```

---

## 6. Multi-model routing (LiteLLM)

```mermaid
flowchart LR
    Agent["Any agent in graph"] --> LiteLLM["LiteLLM router"]

    LiteLLM --> Cache{"Semantic<br/>cache hit?"}
    Cache -->|yes| Return["Return cached"]
    Cache -->|no| Pick

    Pick{"Pick model"}
    Pick -->|"Analyst, Health Coach"| Sonnet["Claude Sonnet 4.5<br/>Anthropic API"]
    Pick -->|"Planner, Scheduler, Aggregator"| Mini["GPT-4o-mini<br/>OpenAI API"]

    Sonnet -->|"error / rate limit"| Fallback["Fallback to<br/>GPT-4o-mini"]
    Sonnet -->|success| Store
    Mini --> Store
    Fallback --> Store

    Store["Cache + return"] --> Agent

    classDef primary fill:#7c6bff,color:#fff
    classDef fallback fill:#ff6b8a,color:#fff
    classDef cache fill:#b8ff6b,color:#000
    class Sonnet primary
    class Fallback fallback
    class Cache,Store cache
```

---

## 7. MCP server topology

```mermaid
flowchart TB
    Graph["LangGraph Scheduler Agent"] -.MCP protocol.-> MCP

    subgraph MCP["athletecore_mcp.py"]
        T1["@tool get_calendar_events"]
        T2["@tool create_training_block"]
        T3["@tool get_performance_history"]
    end

    T1 --> SQL[("SQLite<br/>schedule table")]
    T2 --> SQL
    T3 --> SQL
    T3 --> Q[("Qdrant<br/>user_history")]

    note["Future:<br/>swap SQLite for<br/>Google Calendar API<br/>without changing<br/>agent code"]
    SQL -.future.-> note
```

---

## 8. Evals & A/B pipeline

```mermaid
flowchart LR
    Dataset[("golden_dataset.json<br/>40 cases")] --> Runner

    Runner["run_evals.py"] --> V1
    Runner --> V2

    V1["Analyst v1 · direct prompt<br/>t=0.3"]
    V2["Analyst v2 · chain-of-thought<br/>t=0.2"]

    V1 --> Judge
    V2 --> Judge

    Judge["LLM-as-judge<br/>GPT-4o · 1-5 scale"] --> Metrics

    subgraph Metrics["Aggregated metrics"]
        M1["Relevance avg"]
        M2["Pattern accuracy"]
        M3["Latency p50/p95"]
        M4["Cost per query"]
    end

    Metrics --> Report["Markdown report<br/>+ chart.png"]

    Report --> LangSmith["LangSmith dataset<br/>persist results"]
```

---

## 9. Deployment topology (Demo Days)

```mermaid
flowchart TB
    subgraph Internet
        User["Browser"]
    end

    subgraph Vercel["Vercel · Edge"]
        FE["Static React build<br/>(Vite output)"]
    end

    subgraph Render["Render · backend service"]
        Docker["Docker container"]
        subgraph Docker
            FastAPI["FastAPI on :8000"]
            QdrantSvc["Qdrant on :6333<br/>persistent volume"]
        end
    end

    subgraph SaaS["SaaS services"]
        LS["LangSmith"]
        Sentry["Sentry"]
        Anthropic["Anthropic API"]
        OpenAI["OpenAI API"]
    end

    User -->|HTTPS| FE
    FE -->|api.athletecore.app| FastAPI
    FastAPI --> QdrantSvc
    FastAPI --> Anthropic
    FastAPI --> OpenAI
    FastAPI -.traces.-> LS
    FastAPI -.errors.-> Sentry
```

---

## 10. Frontend component tree (текущий skeleton)

```mermaid
flowchart TD
    App --> Router["BrowserRouter"]
    Router --> AppLayout

    AppLayout --> Backdrop["app-backdrop · grain"]
    AppLayout --> Sidebar
    AppLayout --> Main["main · Outlet"]
    AppLayout --> Drawer["ProfileDrawer<br/>(toggle)"]

    Main --> Analysis["/analysis · AnalysisPage"]
    Main --> Schedule["/schedule · Schedule"]
    Main --> Progress["/progress · Performance"]
    Main --> Health["/health · Health"]
    Main --> History["/history · History"]

    Sidebar --> Nav["nav items · 5 routes"]
    Sidebar --> Agents["Agent status pills"]
    Sidebar --> Chip["Profile chip<br/>(opens Drawer)"]

    Drawer --> BWF["BWFRankCard<br/>(scraped, cached 24h)"]
    Drawer --> Stats["Stats 2x2"]
    Drawer --> Conn["Connections list"]

    Analysis --> Hero["Hero metrics row"]
    Analysis --> AnaBlock["AnalysisBlock<br/>error tags HIGH/MED/LOW"]
    Analysis --> Chat["ChatInput"]

    Schedule --> Switcher["Month/Week/Day"]
    Schedule --> Views["MonthView / WeekView / DayView"]
    Schedule --> Modal["AddEventModal"]
```

---

## 11. State shape (LangGraph)

```python
class GraphState(TypedDict):
    # Input
    user_id: str
    raw_input: str            # transcribed text
    image_b64: str | None     # for Vision

    # Routing
    selected_agents: list[Literal["analyst", "scheduler", "health_coach"]]

    # Per-agent results
    analyst_output: AnalystResult | None
    scheduler_output: ScheduleResult | None
    health_output: HealthResult | None

    # Aggregation
    aggregated_response: str
    proposed_schedule_changes: list[ScheduleChange]

    # HITL
    awaiting_confirmation: bool
    user_decision: Literal["approve", "reject"] | None

    # Metadata
    trace_id: str
    started_at: datetime
    cost_usd: float
```

---

## 12. Цвета и легенда диаграмм

| Цвет | Что значит |
|---|---|
| 🟣 фиолетовый (`#7c6bff`) | Supervisor / основная логика |
| 🟢 лайм (`#b8ff6b`) | Успех / финал / cache |
| 🔴 коралл (`#ff6b8a`) | HITL / fallback / алерт |
| ⚫ тёмный (`#161a24`) | Сервис / специалист |
| 🟡 янтарь (`#ffc83c`) | Внимание / опционально |

---

## 13. Что НЕ нарисовано на диаграммах (намеренно)

- Authentication flow (на MVP — один юзер без auth)
- Rate limiting (через `slowapi` middleware — стандарт)
- Logging (через `structlog` → stdout → Render logs)
- Background jobs (нет в MVP — всё синхронно)

Эти вещи появятся в v0.3 (post Demo Days), когда продукт пойдёт в pilot с несколькими спортсменами.

---

*ARCHITECTURE.md — v0.2 · соответствует `AthleteCore_TZ.md` v0.2*
