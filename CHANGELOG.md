<!-- Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

# Changelog

## [Unreleased]

### 2026-06-14 — Comparison hints, chat scroll, added-country scoring

- Comparison table shows an interaction hint (click a country to explore, a value for its
  rationale, a score for the calculation breakdown).
- Chat now scrolls so the top of the latest assistant reply is at the top of the box
  (read from the start of the answer), pinning to the bottom only while it's thinking.
- Fix: a country added via chat tool-calling or the "add country" button is now scored
  immediately (`rescore_candidates`), so it ranks and shows a match score instead of
  landing unscored at the bottom with a blank cell.

### 2026-06-14 — Chatbot tool-calling

- The chat assistant can now act via OpenAI function calling: set criteria importance
  (weights), apply/clear filters, add a country, select/unselect for comparison, and
  rebuild the shortlist — reusing the existing services so it stays consistent
  (`services/chat_tools.py`, `ai_client.create_with_tools`, tool loop in `chat.reply`).
- `/chat` returns `{reply, changed}`; the board re-reads when the assistant changed it.
  Replaced the streaming chat path with the tool loop.

### 2026-06-14 — Password reset (CLI + admin)

- `./xcape.sh reset-password <env> <email> <newpassword>` (via `app.db.set_password`).
- Admin endpoint `POST /admin/users/{id}/reset-password` (admin-only) and an admin
  users table with a "Reset password" action. Tests added.

### 2026-06-14 — Criteria filters & weights, colour cells, any language, admin, docs

- Criteria filters (hard constraints) in addition to weights: language ("only where I
  can communicate"), climate, visa, and minimum buckets for ordinal criteria
  (`profiles.filters`, migration 0008; `shortlist.passes_filters`). Filters rebuild the
  shortlist pool, so e.g. an Arabic speaker now surfaces Arabic-speaking countries.
- "Criteria settings" panel in the comparison board: per-criterion importance
  (ignore/low/normal/high) and the key filters; applying re-ranks and re-filters.
- Comparison cells are colour-coded by per-user quality (green good / amber weak / red
  no-go) with a legend, replacing the arrows. `quality` tiers added to candidates.
- Language selection is now open-ended (any ISO language via Intl.DisplayNames),
  replacing the fixed 8-language list.
- Admin: `./xcape.sh make-admin <env> <email>` grants admin; the Admin link → /admin.
- Docs: `docs/xcape-design-and-criteria.md` (palette, colour coding, criteria
  definitions, scoring, filters, data sources, admin).

### 2026-06-14 — Context-aware, streaming chat

- The chat is now a real conversation: each turn includes a compact briefing of what we
  know (name, residence, citizenships, household, reasons, budget, climate, languages,
  priorities, and the shortlist being compared) plus the recent message history — it no
  longer starts fresh each question.
- Streaming: answers stream token-by-token (`/searches/{id}/chat/stream`, plain-text
  chunks; `ai_client.converse_stream`) so text appears immediately instead of after the
  full reply. The streaming generator uses its own DB session (the request session is
  torn down before a StreamingResponse generator runs).
- Frontend appends deltas live into the assistant bubble; "thinking" spinner shows only
  until the first token.

### 2026-06-14 — Score explanation

- Clicking a score in the comparison board opens a breakdown of how it was derived:
  per criterion, the country's quality (0-100), the weight (with a "priority" marker
  for user-boosted criteria), and the contribution in points — which sum to the score.
  New `shortlist.explain_candidate` + `/searches/{id}/candidates/{cid}/explanation`.

### 2026-06-14 — Citizenship-aware visa scoring, Markdown chat, source labels

- Citizenship vs residence: the household's citizenship(s) (user + spouse/children) are
  captured separately from the country of residence (`users.citizenships`, migration
  0007) and drive visa / ease-of-movement scoring — a citizen of the destination or an
  EU/EEA/CH citizen moving within that zone scores free movement, while a non-EU
  resident (e.g. a US citizen in France) does not. Onboarding step + profile field
  (localized country multi-select); editing citizenship re-scores. Tests added.
- Chat answers are now requested as Markdown and rendered with react-markdown
  (sanitized) — no more run-on paragraphs.
- Drill-down sources now show the site name (hostname) as the link instead of
  "Source 1/2/3"; inline URLs are kept out of the summary (prompt + display cleanup).

### 2026-06-14 — All countries, interactive discriminator, AI spinners

- Seed expanded from a sample to **every country** (217) — generated from World Bank
  (roster, capital, region, coords, income) + Wikidata (official languages). The
  curated 27 keep their hand-tuned attributes; generated countries get coarse honest
  attributes (climate from latitude, cost/healthcare from income, languages), with the
  rest left for AI to fill on demand. AI results are cached on the Place
  (`facts`, `criteria_detail`, attributes via research) and as `MediaAsset` rows.
- "Help me narrow down" is now interactive: each question targets a scoring criterion
  with localized options carrying an importance weight; clicking sets that weight,
  re-scores and re-ranks, and the scores in the table update. (Previously did nothing
  and showed English options.)
- Animated spinner during AI operations: chat, add-country research, narrowing,
  drill-down detail/links.
- Removed the nginx reminder from `deploy prod`.

### 2026-06-14 — Editable profile & rich country drill-down

- Profile editor at `/profile` (header link): all desiderata — name, current country,
  household, reasons, budget, rent/buy, climate, known languages, priorities — visible
  and editable any time. Saving re-scores and re-ranks every existing search
  (`shortlist.rescore_candidates`), preserving each search's chosen candidates and
  selection. Shared option vocabulary + `Chip` between onboarding and the editor.
- Drill-down rebuilt: basic facts (capital, population, region, flag) from keyless
  World Bank + flagcdn; an **inline OpenStreetMap** map and an **inline photo** (capital
  city's Wikipedia lead image); AI per-criterion detail **with source links** (cached
  per language); other resources as a link list. New `Place.facts` / `criteria_detail`
  caches (migration 0006), `services/country_facts.py`, and `/places/{id}/facts` +
  `/places/{id}/detail` endpoints.

### 2026-06-14 — Language-aware scoring

- Onboarding now asks which languages the user already speaks (multi-select,
  pre-filled from their locale) alongside the willingness-to-learn question; stored as
  `language_skills = { known: [...], willing_to_learn }`.
- Each country carries a `languages` list (official + widely-spoken English). The
  shortlist scores language ease against the user's known languages: a match → full
  value; otherwise it falls back to learn-difficulty, softened if willing to learn.
  AI place research returns `languages` too.
- Verified: a Spanish speaker surfaces Spanish-speaking countries; an English speaker
  surfaces English-usable ones.

### 2026-06-14 — Shortlist selection, full localization, conservative reads

- Shortlist: user picks up to 5 countries for the comparison board via checkboxes
  (top 5 pre-selected). Selection is server state (`candidates.selected`, migration
  0005; server enforces the max-5 cap), re-read after every toggle. The comparison
  board shows exactly the selected set; "×" there unselects (keeps it in the shortlist
  for reselection).
- Full i18n: localized all attribute values (low/medium/high, mild, strong, …) via a
  `values` map, the admin page, and the voice-button messages. Country names render in
  the active language via `Intl.DisplayNames` on the ISO code (Spain → Espagne,
  United States → États-Unis). Swept pages for hard-coded strings.
- Conservative reads: comparison-board mutations (add criterion, remove/​unselect,
  add country) now re-read candidates from the server instead of trusting local state;
  onboarding re-reads identity after updating it.

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
