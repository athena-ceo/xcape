<!-- Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

# xCape — Architecture & Implementation Plan

> Companion to `docs/xcape-requirements-high-level.md`. This document records the
> agreed design decisions, the data model, the API surface, the screen inventory,
> and the deployment plan. It is the artifact to review **before** feature work.

## 1. Confirmed decisions

| Topic | Decision |
|-------|----------|
| Search depth | Built-in DB covers **countries + major regions**; cities/neighbourhoods are researched by AI on demand and cached back. |
| Language | **Bilingual French + English, default French.** Every user-visible string localized in both (`src/i18n/{fr,en}.ts`). |
| Database | **Postgres everywhere** (dev + prod) via Docker, matching golden-path. |
| AI provider | **OpenAI Responses API**, default model `gpt-5`, used for web search + tool calls. |
| AI strategy | **Cache-first.** Built-in `Place` data serves the baseline + initial shortlist with no AI call. AI is used only for discriminating questions, on-demand criteria/countries, drill-down media, and the scoped chat. Results are cached back into the DB with a freshness timestamp. |
| Auth | Simple self-registration + password (bcrypt). JWT bearer tokens. Email verification optional (auto-verify in dev). |
| Real-estate handoff | Web search only for now (future business model). |
| Ports (prod) | backend **8030**, frontend **3030** — distinct from golden-path's 8020/3020. Internal Postgres not published on host. |

## 2. Tech stack & repository layout

Mirrors golden-path conventions (FastAPI / SQLAlchemy / Alembic backend; Vite +
React + TS + Tailwind frontend; Docker compose; an ops script at repo root).

```
xcape/
├── docs/                         # requirements, this plan, decisions log
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/                  # migrations
│   ├── app/
│   │   ├── main.py               # FastAPI app + router mount + CORS + health
│   │   ├── core/                 # config, security, logging
│   │   ├── db/                   # engine, session, Base, init/seed
│   │   ├── models/               # SQLAlchemy ORM models
│   │   ├── schemas/              # Pydantic request/response models
│   │   ├── api/
│   │   │   ├── deps.py           # auth dependencies (get_current_user, require_admin)
│   │   │   └── v1/               # routers: auth, profile, search, places, candidates, chat, admin
│   │   ├── services/             # ai_client, place_research, shortlist, chat, media
│   │   └── data/                 # bundled seed data (countries + regions JSON)
│   └── tests/
├── src/                          # React frontend (golden-path keeps it at repo root)
│   ├── main.tsx, App.tsx
│   ├── pages/                    # Home, Login, Register, Onboarding, Shortlist, Comparison, Drilldown, Admin
│   ├── components/               # shared UI (VoiceInput, CriteriaTable, CandidateCard, ...)
│   ├── services/                 # api client, auth
│   ├── store/                    # zustand stores (auth, search)
│   └── i18n/                     # fr.ts, en.ts, index.ts, context
├── docker-compose.dev.yml
├── docker-compose.server.yml
├── xcape.sh                      # ops wrapper (start/stop/rebuild/status/logs/migrate/seed/backup-db)
├── nginx/xcape.conf.example      # external nginx server block for apps.athenadecisions.com
└── CLAUDE.md, README.md, .gitignore, env templates
```

## 3. Data model

Core entities (SQLAlchemy models under `backend/app/models/`):

- **User** — `id, email (unique), password_hash, is_admin, is_verified, locale, created_at, last_login_at`.
- **Profile** — 1:1 with User. The relocation baseline:
  `household_type` (single/couple/family), `reasons_leaving` (JSON list), `origin_country`,
  `budget_monthly`, `tenure` (rent/buy), `climate_pref`, `language_skills` (JSON),
  `must_haves`/`nice_to_haves` (JSON), `criteria_weights` (JSON), `updated_at`.
- **Search** — a user's working session (a user may have several). Holds the live state:
  `id, user_id, title, status, criteria_set (JSON ordered list of criterion keys),
  notes, created_at, updated_at`.
- **Place** — the built-in, AI-refreshable database. One row per country **or** region:
  `id, kind (country/region), parent_id (region→country), name, iso_code,
  attributes (JSON: cost_of_living, climate, language, healthcare, safety,
  political_stability, tax, visa, …), summary_fr, summary_en,
  source (seed/ai), freshness_at`.
- **Candidate** — a Place pinned into a Search: `id, search_id, place_id, status
  (active/removed), match_score, per_criterion (JSON cached values), rank, pinned_at`.
- **MediaAsset** — drill-down media discovered via web search, cached per Place:
  `id, place_id, type (map/photo/link), url, caption, source, created_at`.
- **ChatMessage** — scoped chat history per Search: `id, search_id, role, content,
  tokens, created_at`.
- **AIQueryLog** — admin observability: `id, user_id, kind, model, prompt_summary,
  tokens_in, tokens_out, latency_ms, cost_estimate, created_at`.

Every model change ships with an Alembic migration (idempotent `IF NOT EXISTS`
guards) and a constraint test, per golden-path discipline.

## 4. API surface (`/api/v1`)

| Group | Endpoints |
|-------|-----------|
| auth | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` |
| profile | `GET /profile`, `PUT /profile`, `POST /profile/onboarding-step` |
| search | `GET /searches`, `POST /searches`, `GET /searches/{id}`, `PATCH /searches/{id}` |
| shortlist | `POST /searches/{id}/shortlist` (instant, seed-driven), `POST /searches/{id}/discriminate` (AI questions) |
| candidates | `GET /searches/{id}/candidates`, `POST …/candidates` (add country), `DELETE …/candidates/{cid}`, `POST …/criteria` (add criterion, fans out to all candidates) |
| places | `GET /places`, `GET /places/{id}`, `GET /places/{id}/media` (AI/web on miss), `POST /places/{id}/refresh` (admin) |
| chat | `POST /searches/{id}/chat` (scoped, streamed), `GET …/chat` |
| voice | `POST /voice/transcribe` (audio → text, OpenAI) |
| admin | `GET /admin/users`, `GET /admin/searches`, `GET /admin/ai-log`, `GET/PUT /admin/places` |

All routes require an auth dependency; admin routes require `require_admin`.

## 5. AI integration

A single `services/ai_client.py` wraps the **OpenAI Responses API** (`gpt-5`), with:
- a thin call helper that records every call to `AIQueryLog`;
- the **web_search** tool enabled for place research, media, and chat;
- structured-output schemas for shortlist/discriminator results so the backend gets
  validated JSON, not free text;
- a strict system prompt for chat that limits scope to the user's profile, candidates,
  and relocation topics — **political stability/trends of target countries are in
  scope** (per requirements), off-topic requests are politely declined.

Cache-first flow: shortlist and baseline comparisons read `Place`/`Candidate` rows
directly. AI is invoked only on a cache miss or an explicit "refresh / add / ask".

## 6. Screen inventory (frontend)

1. **Home / landing** — welcoming turquoise hero, self-register / login.
2. **Onboarding** — progressive one-question-at-a-time baseline (mock-up #1), voice input.
3. **Shortlist** — 10–20 instant candidates from seed data, with reasons.
4. **Discriminate** — AI-generated differentiating questions to narrow to 3–5.
5. **Comparison playground** — the spreadsheet centerpiece (mock-up #2): editable
   criteria, add/remove countries & criteria, match scores, scoped chat sidebar.
6. **Candidate drill-down** — maps, photos, neighbourhoods, "find an agent" web search.
7. **Account** — profile, saved searches (return to context).
8. **Admin** — users, searches, place DB editor + refresh, AI usage log (golden-path style).

Voice input (`components/VoiceInput`) uses the browser MediaRecorder → `/voice/transcribe`
for questions and chat, important on mobile.

## 7. Deployment

- **Dev:** `docker-compose.dev.yml` — Postgres, backend (uvicorn --reload on :8030→8000),
  Vite frontend (:3030→5173). `./xcape.sh start dev`.
- **Prod (apps.athenadecisions.com):** `docker-compose.server.yml` — backend :8030,
  frontend :3030, internal Postgres (not host-published). External nginx gets a new
  `xcape.athenadecisions.com` server block (`nginx/xcape.conf.example`) proxying to 3030/8030.
  No port collision with golden-path (8020/3020).

## 8. Build phases (after scaffold approval)

1. **Foundation** — auth, profile, onboarding, seed `Place` DB (countries + regions), instant shortlist. *(thin vertical slice runnable)*
2. **Comparison playground** — candidates, criteria fan-out, match scoring, drill-down.
3. **AI layer** — discriminator questions, on-demand research, media, scoped chat, voice.
4. **Admin** — dashboards, place editor, AI log.
5. **Hardening** — tests, i18n completeness, nginx + prod compose, freshness refresh job.

## 9. Open items to confirm later

- Final public hostname (`xcape.athenadecisions.com`?) and TLS handling on the external nginx.
- Email provider for verification/reset (reuse golden-path's, or auto-verify only).
- Seed data breadth for v1 (which countries/regions to ship first).
