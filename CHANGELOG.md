<!-- Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

# Changelog

## [Unreleased]

### 2026-06-14 — CI: smoke tests on every push

- GitHub Actions (`.github/workflows/ci.yml`) on push + PR to main, three jobs:
  backend pytest, frontend type-check + build, and an end-to-end Docker smoke test
  (build stack → migrate → seed → `scripts/smoke_test.py`).
- `scripts/smoke_test.py`: validates health, registration (names + current-country
  default), profile, instant shortlist (sorted, non-empty), current-country baseline +
  `vs_current` deltas, and graceful chat without an API key. Reusable via
  `./xcape.sh smoke`, and run as the final gate of `./xcape.sh deploy prod`.

### 2026-06-14 — Paired voice + text everywhere

- New `VoiceButton` (standard microphone icon, filled red while recording) and
  `VoiceField` (text input with an inline mic). Dictation appends to typed text.
- Every free-text field now offers both text and voice: login email, registration
  first/last name + email, onboarding current country, comparison add-country and chat.
  Password stays text-only (security); budget is a numeric stepper.
- Removed the old no-op standalone mic (voice without a paired text field) and the
  `●`-dot icon; replaced with the microphone icon throughout.

### 2026-06-14 — User identity & current-country baseline

- Users now have `first_name`, `last_name` and `current_country` (migration 0004).
  Registration captures names and defaults the current country: geo-IP
  (`services/geo.py`, best-effort) → locale (fr→France, en_gb→UK, en_us→USA, …) →
  France. Editable via `PATCH /auth/me` and the onboarding flow.
- Current country is the systematic comparison baseline: candidates are annotated
  with `vs_current` (better / worse / same per ordinal criterion vs the current
  country). New `services/comparison.py`; baseline resolved via
  `GET /searches/{id}/baseline` (AI-researched + cached for non-seeded origins).
  France added to the seed as the default reference.
- Frontend: registration collects first/last name; onboarding adds a current-country
  step (pre-filled from the detected value); comparison board shows a current-country
  column with ↑/↓/= indicators per candidate.
- Tests: identity capture, current-country default, `PATCH /auth/me`, delta direction,
  candidate annotation (14 backend tests passing).

### 2026-06-14 — Production deploy & path-based serving

- `./xcape.sh deploy prod`: pre-deploy backup, git pull, build, up, migrate, seed,
  health check (mirrors golden-path's deploy).
- Path-based serving at `apps.athenadecisions.com/xcape`: Vite `base` + router
  `basename` driven by `VITE_BASE_PATH`; `nginx/xcape-apps-location.conf` with the
  location blocks to paste into the shared apps server (180s proxy timeouts for the
  long AI calls). Configurable CORS origins. Subdomain path stays available via
  `nginx/xcape.conf.example` + `XCAPE_BASE_PATH=/`.
- Project allowlist: standard unix text tools + docker commands.

### 2026-06-13 — Phase 3: AI layer (OpenAI Responses API)

- Upgraded OpenAI SDK to 2.41.1 (the pinned 1.57 predated the Responses API).
- `ai_client`: Responses API wrapper with web search, strict JSON-schema structured
  output, and per-call logging to `AIQueryLog` (model, kind, tokens, latency).
  Structured calls default to `reasoning_effort=low` to keep latency reasonable.
- On-demand place research: adding a country not in the seed DB researches its full
  attribute set via web search and caches it (`source="ai"`). Adding a criterion that
  is missing from seed data fills the value per place via AI.
- Drill-down media: `/places/{id}/media` discovers a maps link, official/relocation
  links and photo references via web search, cached as `MediaAsset` rows
  (widened `media_assets.source` to Text — migration 0003).
- Discriminator questions: `/searches/{id}/discriminate` returns 3-5 bilingual
  questions (with options) that best split the current shortlist.
- Scoped chat now calls the real API (web search + relocation-only system prompt,
  political-stability questions allowed) with graceful degradation when no key.
- Voice transcription wired (`/voice/transcribe`).
- Frontend: functional chat panel, add/remove country, add criterion, "help me narrow
  down" discriminator panel, and a candidate drill-down page with media. New i18n.

### 2026-06-13 — Phase 1: onboarding flow & richer shortlist

- Full progressive onboarding wizard (7 steps): household, reasons for leaving,
  budget, rent/buy, climate, language willingness, top priorities — with progress
  bar, back/continue, and voice affordance. Bilingual FR/EN.
- Richer place seed data: 27 countries with a consistent 11-attribute schema
  (cost, climate, language ease, healthcare, safety, political stability, tax, visa,
  expat community, nature, internet) + regions and bilingual summaries.
- Shortlist scoring v2: blends per-criterion quality with the user's priorities —
  reason-for-leaving weight boosts (avoid same problems), household adjustments,
  climate matching, language-learning willingness. Returns human-readable
  match reasons (new `candidates.match_reasons` column, migration 0002).
- Shortlist UI shows match-reason chips; comparison board uses localized criteria.
- Tests: profile partial-update accumulation, profile-driven shortlist ranking
  (9 backend tests passing).

### 2026-06-13 — Project scaffold

- Architecture & plan document (`docs/xcape-architecture-and-plan.md`).
- Backend: FastAPI app, SQLAlchemy models (user, profile, search, place, candidate,
  media, chat, ai_log), Pydantic schemas, JWT auth (bcrypt), API v1 routers
  (auth, profile, search, candidates, places, chat, voice, admin), services
  (ai_client, shortlist, chat, place_research), Alembic setup + initial migration,
  bundled place seed data (12 countries + regions), pytest suite (6 passing).
- Frontend: Vite + React + TS + Tailwind, bilingual FR/EN i18n (default FR), turquoise
  theme, auth store, API client, pages (Home, Login, Register, Onboarding, Shortlist,
  Comparison playground, Admin), VoiceInput component.
- Ops: `xcape.sh`, dev + server Docker compose, external nginx example, env template.
  Ports 8030 (backend) / 3030 (frontend).
