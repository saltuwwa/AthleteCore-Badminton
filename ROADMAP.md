# AthleteCore — Roadmap

Honest roadmap aligned with current MVP and [CHECKLIST.md](CHECKLIST.md).

---

## 1. Current MVP (course defense)

- [x] LangGraph multi-agent chat with semantic router
- [x] SQLite LTM + write-gate + past-event guard
- [x] Qdrant methodology RAG + lexical fallback
- [x] Whisper voice → chat pipeline
- [x] MCP server (4 tools) + Cursor skill
- [x] Safety eval (25 cases) + ~195 pytest tests
- [x] Langfuse tracing
- [x] React chat UI + defense PDF (`docs/athletecore_defense_presentation.pdf`)
- [x] Document upload analysis (Gemini)
- [x] Video analysis MVP (pose / metrics)

---

## 2. Short-term improvements (post-defense)

- [ ] HITL schedule UI — confirm/reject `pending_confirmation` in frontend
- [ ] Replace mock pages (`/history`, `/schedule`, `/progress`, `/health`) with API data
- [ ] Expand safety golden dataset to 50–100 cases
- [ ] Analyst golden dataset + automated runner
- [ ] Offline A/B: RAG on/off, router thresholds (documented harness)
- [ ] SKILL + docs sync after each major graph change

---

## 3. Production hardening

- [ ] Authentication and multi-user `user_id`
- [ ] Secrets management (no keys in local `.env` commits)
- [ ] Rate limiting and abuse protection on `/api/chat`
- [ ] Deploy backend (e.g. Render) + frontend (Vercel) with env parity
- [ ] Error tracking (Sentry or equivalent)
- [ ] Backup / migration strategy for SQLite → Postgres (optional)

---

## 4. Better evals

- [ ] LLM-as-judge on offline dialog samples (helpfulness, faithfulness)
- [ ] Retrieval @k benchmarks on methodology queries
- [ ] CI: safety eval + pytest on every PR
- [ ] Langfuse scores / datasets linked to traces
- [ ] Video quality eval beyond debug JSON

---

## 5. More real athletes

- [ ] Onboarding flow (sport, level, goals)
- [ ] Privacy consent and data export/delete
- [ ] Coach read-only view of athlete memories (scoped)

---

## 6. Coach dashboard

- [ ] Team roster and shared schedule
- [ ] Review pending AI proposals
- [ ] Annotate analyst JSON errors → training plan
- [ ] Aggregate fatigue / load signals (non-medical)

---

## 7. Federation / B2B2C

- [ ] Federation license for methodology corpus
- [ ] White-label frontend
- [ ] Analytics for national teams (aggregated, GDPR-aware)

*Not started — product direction only.*

---

## 8. Multi-sport expansion

- [ ] Abstract `sport` field and session types beyond badminton
- [ ] Sport-specific skills and RAG collections
- [ ] Separate vector collections per sport

---

## Documentation maintenance

When shipping features, update:

- [README.md](README.md) Current Status
- [ARCHITECTURE.md](ARCHITECTURE.md) diagrams
- [CHECKLIST.md](CHECKLIST.md) evidence column
