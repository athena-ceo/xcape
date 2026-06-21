<!-- Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

# Changelog

## [Unreleased]

### 2026-06-16 — Service criteria: quality + access sub-scores, filter on one

- Healthcare & education now use a **service lens**: the eval returns a headline score plus
  separate **quality** and **access** sub-scores (e.g. Germany healthcare 78 = quality 86,
  access 65), stored in `meta` and shown in the drill-down. The headline blends both, so a
  world-class service newcomers can't easily get no longer scores top.
- You can **filter on one component** — e.g. require healthcare *access* ≥ good regardless of
  quality — via a `key:component` filter (`healthcare:access`). Surfaced as an Overall/Quality/
  Access selector in Criteria settings; it follows the parent criterion's weight (dormant at
  weight 0) like any filter. Eval prompt v7.

### 2026-06-16 — Structured incident-trend data (level + trajectory)

- Trend-sensitive criteria (`safety`, `political_stability`, and the per-community "Safety for
  my community") now use a dedicated **trend lens**: the eval captures structured
  `{level, trend, window, metric}` (e.g. anti-community incidents high/low and improving/stable/
  worsening, with a one-line factual basis citing a recognised monitor — ADL/CST, ILGA,
  OSCE-ODIHR/FRA, national stats). The 0–100 score reflects BOTH level and trajectory.
- Stored in `place_custom_evals.meta` (migration `0020_eval_meta`), round-trips through
  export/seed, and shown in the drill-down as a level + trend arrow (↗/→/↘) + window + basis.
- Design for a grounded data pipeline (option B) documented in
  `docs/xcape-incident-trend-data.md`.

### 2026-06-16 — Foreign-resident-access prompts; prompt-versioned eval cache
- Refined: criteria now use one of two **lenses** — ACCESS (healthcare, education, tax,
  asset security, banking, …: can a newcomer qualify/afford/reach it) vs EXPERIENCE (culture,
  food, nature, internet, …: lived quality for a settled newcomer), so the access framing isn't
  forced onto experiential criteria. healthcare/education descriptions sharpened to access.
- Prompts (eval + detail) and the shared research `_SYSTEM` are now **origin-neutral** — no
  hard-coded home country / citizenship — because the eval cache is shared across users. The
  per-user home country stays in the chatbot context, where it belongs. (Eval version → v3,
  detail version → v3.)


- **AI prompts now judge access for a FOREIGN RESIDENT**, not generic domestic quality — for
  every criterion (healthcare, education, banking, …) the score and the drill-down text reflect
  eligibility, qualifying/waiting periods, cost to non-citizens, language and legal hurdles for
  a newcomer. (Eval prompt in `criterion_eval`, detail prompt in `place_research`.)
- **Prompt changes auto-dirty the cache.** Each cached eval stores a `prompt_fp` fingerprint of
  (prompt version + criterion label + description); when the prompt or wording changes the
  fingerprint changes, so `evaluate-all` (and lazy refresh) regenerate exactly the affected
  rows — no manual cache-clearing, and a plain deploy still clobbers nothing. The fingerprint
  round-trips through `export-evals` / seed. Drill-down detail text is versioned the same way
  (entries from an older prompt are ignored and regenerated). Migration `0019_eval_prompt_fp`.
- Removed dead legacy bulk-detail code (`fetch_criteria_detail` + helpers).
- Removed the redundant `criteria` i18n dictionary; criterion labels come solely from the
  registry now (drill-down, profile and onboarding all resolve via `labelOf`).

### 2026-06-16 — User-feedback round: trustworthy defaults, less tweaking

- **Persona derivation fixed**: cost-of-living / economic reasons are no longer read as wealth
  protection (a frugal family was being classed as "asset protection"). `economy`→career,
  `cost`→affordability; `asset_protection` is reserved for explicit "patrimoine".
- **Persona key criteria are exclude-bad filters by default** — countries rated À éviter on a
  persona's critical criteria drop off automatically (e.g. Malaysia for Jewish-community
  safety), so the first result is plausible with no manual setup. Loosen via the relax banner.
- **Onboarding resets stale filters** (and applies the persona's), fixing carried-over criteria
  for returning users.
- **Two new personas** — "Aventure entrepreneuriale", "Élargir mes horizons" — in the picker.
  Relabels: "Stabilité politique et libertés" (was "Liberté politique"); Visa →
  "Facilité d'installation (visa)".
- **Board**: "Show other criteria" now expands the relevant category rows (was a no-op to the
  eye); the home country gets an overall score (so "stay put" is a visible conclusion);
  criteria values carry a persistent dotted underline (clearly clickable); "Repeupler" →
  "Actualiser la liste".

### 2026-06-16 — Explicit add/remove of a country overrides filters; excluded bar

- **Adding a country pins it.** A country you add (even one that violates a hard filter, e.g.
  Israel under a strict visa filter) now stays on the board: it's marked as an explicit
  override (`Candidate.override = "in"`) so self-heal-on-load and repopulate keep it instead
  of silently dropping it. It still shows the amber ⚠ flag on the criterion it misses, plus a
  📌 "Added by you" badge so the intent is clear.
- **Removing a country excludes it.** The × button now banishes the country (`override =
  "out"`) instead of merely unselecting it, so scoring/filters/repopulate never re-add it
  (previously a removed country like Portugal would reappear on the next re-rank).
- **New "Excluded" bar** under the comparison table lists everything you removed, with a
  one-click restore that returns it to the neutral ranked pool.
- New endpoints `POST /searches/{id}/candidates/{cid}/exclude` and `…/restore`; `CandidateOut`
  now carries `override`. Migration `0018_candidate_override` adds the nullable column.

### 2026-06-16 — Deploy seeding is insert-only; `reseed-data` to force a refresh

- `seed` (and therefore `deploy prod`) is now **insert-only**: it bootstraps a fresh DB and
  adds newly-committed countries, but **never overwrites existing places or evals**. So a
  redeploy no longer re-applies the whole country snapshot — it's a true no-op once the data
  is in place, and can't clobber prod-side data.
- New `./xcape.sh reseed-data <dev|prod>` force-refreshes country data (places + cached
  evals) from the seed files, overwriting existing rows — use it to push committed data
  updates (refreshed evals, corrected attributes). User searches/profiles and custom-criterion
  evals are never touched. Mirrors the `reseed-criteria` pattern.
- New `./xcape.sh verify-evals <dev|prod>` (read-only) reports whether the live criterion
  evals match the committed seed (i.e. whether the recalibration is present) — match / differ
  / missing — so you can tell if `reseed-data` is needed.

### 2026-06-16 — Hard filters exclude violators; advice on what to relax

- A hard filter now **removes** every country that violates it from the board and replaces
  it with the best **passing** countries by score — filters are exclusionary, as expected,
  rather than keeping violators on the board with a flag.
- When fewer than a full board qualify, a banner reports how many match and suggests the
  single most useful filter to relax — the one admitting the **highest-scoring** otherwise-
  excluded country (with how many it would add), with an "Adjust filters" shortcut. If none
  qualify, it says so explicitly.
- New `GET /searches/{id}/filter-advice` backs the banner. The initial shortlist also
  excludes violators (no more silent fall-back to the unfiltered pool).
- **The board now self-heals on plain page load**: `GET /candidates` re-ranks if the stored
  board still holds filter violators (e.g. a filter set in a previous session), so a reload
  reflects the filters without needing an explicit Repopulate. This was the reason the
  exclusion appeared not to work — the load path returned the stale board untouched.

### 2026-06-16 — Weight 0 ignores a criterion entirely (filter goes dormant)

- A criterion with **importance 0 is now ignored completely — its hard filter no longer
  applies**. Previously "weight 0" (don't care) plus an active filter (must satisfy)
  contradicted each other: a persona that zeroes, say, Climate would still flag every
  country whose climate didn't match a leftover `climate = temperate` filter. Effective
  weight folds in persona/defaults + your overrides, so a normal user's default filters
  (climate/visa/language all have positive default weights) keep working.
- **Criteria settings** now shows "Ignored — importance is 0" (dimmed) next to a filter
  whose criterion is at weight 0, so the dormant state is visible.
- The specific **leaf cell** that fails an active filter shows the ⚠ flag + amber highlight
  (matching the category roll-up), so a flagged category always has a visible culprit row.

### 2026-06-16 — `reseed-criteria` op to roll out registry changes

- New `./xcape.sh reseed-criteria <dev|prod>` overwrites the editable criteria registry
  (criteria tree, personas, communities) from the bundled `criteria.json`. `seed`/`deploy`
  intentionally leave an existing registry untouched (to preserve admin edits), so this is
  how registry changes — e.g. the new personas/communities — get rolled out to an
  environment. It prompts for confirmation and warns that it replaces admin UI edits.

### 2026-06-16 — Fix: custom-criterion weight/min edits silently reverted

- Editing a **custom criterion's importance or threshold** (in Criteria settings or via the
  inline stepper) now actually persists — including setting a weight to **0** to hide it.
  The update mutated the JSON column in place, leaving old == new, so SQLAlchemy emitted no
  UPDATE and the change reverted to its previous value on the next read (no error shown).
  Fixed with a deep copy + `flag_modified`; added an API regression test.

### 2026-06-15 — Inline weight changes re-rank the full country pool

- Adjusting a **built-in criterion's weight** with the inline stepper now **re-ranks every
  country**, so raising a weight can surface countries that newly rank onto the board —
  previously it only re-scored the existing five (custom-criterion edits and the Repopulate
  button already re-ranked, so this removes that inconsistency).
- Note (not a bug): the board still tends to lead with well-rounded, accessible destinations
  because the computed criteria (cost of living, visa ease, proximity) legitimately favour
  them. All ~217 countries carry fresh, balanced AI criterion values — strong non-original
  countries (Singapore, Luxembourg, Norway…) score competitively and rise when you weight
  the criteria they excel at.

### 2026-06-15 — Criteria Settings: Apply / Cancel guard against losing edits

- The **Criteria settings** panel now has explicit **Apply** and **Cancel** buttons, and shows
  an "unsaved changes" hint while edited. Apply is disabled until something changes; Cancel
  (or "Close" when clean) reverts the draft and closes.
- While the panel has **unsaved edits**, the other board actions — **Tune by situation**,
  **Repopulate**, **PDF report** and the Settings toggle — are **disabled**, so clicking
  Repopulate can no longer silently discard in-progress weight/filter changes.
- The draft no longer resyncs from server state while you are editing (a background re-score
  or stray re-render can't wipe edits in progress).
- After **Apply**, the panel now stays open and refreshes to show the saved values, and the
  toolbar re-enables — fixing a bug where Apply left every button greyed out and gave no
  confirmation the change had taken effect.

### 2026-06-14 — Collapsible categories persist; no unjustified drill-down scores

- Comparison-table categories are **collapsed by default** and the expand/collapse state is
  **remembered across refreshes** (localStorage).
- Drill-down no longer shows a precise `NN/100` for a criterion with **no justification**
  (e.g. a score derived only from a coarse seed bucket, not yet AI-evaluated): the score is
  hidden and a "detailed assessment coming" note is shown until the eval is populated.
  **Proximity** now carries a real distance-based justification (≈ km from the current
  country + rough flight time).

### 2026-06-14 — Phase 2: data-driven criteria tree, tags, persona content, AI selection

- **Single-source registry** (`app/data/criteria.json`, served by `GET /criteria`): a
  multi-level tree (categories → leaves), cross-cutting **tags** (personas financial/fear +
  concerns), reason→tags map, communities, value scales, default weights and persona-framed
  AI descriptions. Backend (`services/criteria.py`) and frontend (`services/criteria.ts` +
  `useCriteria`) both read it — the hard-coded criteria/label lists are retired. New leaves:
  tax_treaty, asset_security, proximity. **Open-set principle:** every dimension is an
  initial seed, extendable as data / per-search; new members are first-class.
- **Tag-driven prioritisation**: reasons/priorities map to tags and up-weight every leaf
  carrying them (replaces the hand-maintained reason→criterion table). **Proximity**
  computed from country centroids (haversine) vs the user's current country.
- **Table & control**: collapsible category groups with per-country roll-up colour, leaves
  revealed on expand, registry value labels (Proximity Near/Far). CriteriaSettings: numeric
  importance (0–5) + presets, multi-select climate filter. Rent/buy dropped from onboarding.
- **AI criterion-selection (hybrid)**: pick concern/persona tag chips and/or describe your
  situation in free text → `gpt-5-mini` (`services/criteria_select.py`, endpoint
  `POST /searches/{id}/suggest-criteria`) sets the matching importance weights and proposes
  custom criteria. ("Tune by situation" panel on the board.)

### 2026-06-14 — New request (reset) + PDF report

- **New request / start over**: a header action that truly resets — it wipes the user's
  profile and all their searches (account kept) and reopens a blank questionnaire. Backend
  `POST /profile/reset` + admin `POST /admin/users/{id}/reset` (a "Reset data" button on the
  admin users table) for an admin-level reset of any user. The shared cross-user evaluation
  cache is untouched. (Onboarding still pre-fills from the saved profile when editing via
  the Profile page — the reset path starts blank.)
- **PDF report**: a "PDF report" button on the comparison page downloads a server-built
  report (ReportLab) of the current search — profile summary, the comparison table (0-100
  per criterion + match scores), and per-country details with each criterion's score,
  justification and sources. Endpoint `GET /searches/{id}/report.pdf`.

### 2026-06-14 — Unified per-criterion AI eval cache + data completeness (feedback P1)

Addresses the root cause behind much of the 2026-06-14 feedback: ~190 of 217 countries had
no values for 8 core criteria, so they clustered at neutral and a handful dominated.

- **Unified evaluation cache**: every objective criterion (safety, taxation, healthcare,
  …) and every custom criterion is AI-scored 0-100 per country with a bilingual
  justification + sources, cached cross-user in `place_custom_evals` and shared. New
  `services/criteria.py` registry (objective vs computed leaves) + generalized
  `services/criterion_eval.py` (was `custom_criteria.py`). Scoring prefers the numeric eval
  and falls back to the coarse seed bucket; this is how the seed-sparse countries get real
  values and the shortlist diversifies. Evals run on the faster `gpt-5-mini` (~11s/cell).
- **Progressive population**: `./xcape.sh evaluate-all [--force] [--stale-days N]` fills the
  whole grid (cache-first, resumable); admin `POST /admin/places/{id}/refresh-evals`; and
  on-demand `POST /searches/{id}/evaluate-pending` fills a few board cells per call.
- **Optimistic UI**: adding a country / custom criterion returns immediately with cells
  shown as **pending** (spinner); the board polls `evaluate-pending` and fills cells live,
  with a reassuring waiting line (rotating messages + elapsed timer, `Waiting.tsx`). The
  pop-up shows the cached score + justification instantly for all criteria.
- **Add-country picker**: searchable list with substring filter (resolves French names like
  "Espagne" → Spain); clear "board is full" feedback at 5 countries (fixes the silent
  no-op).

### 2026-06-14 — Chat can replace the comparison set

- Fix: asking the assistant to "propose a new set of countries" updated its message but not
  the table — it described a proposal without acting. New `set_comparison` tool replaces the
  board with a specific set of countries (researches unknowns, selects exactly those,
  re-ranks). The chat system prompt now instructs the assistant to APPLY search changes via
  tools (and to call `set_comparison` whenever it proposes a new set), not just describe them.

### 2026-06-14 — Custom criteria: name + description + score

- A user-defined criterion now has a **short name** (the table column) and an optional
  **longer description** that guides the AI prompt — two fields in the add-criterion UI.
- The AI evaluation now returns a **0-100 score** (plus the bilingual justification and
  sources); the score drives the ranking value (finer than the old good/ok/bad buckets,
  with the colour tier derived from it) and is shown alongside the justification in the
  explanation pop-up. `place_custom_evals.score` (migration 0012); old rows fall back to
  the level. The pop-up now also uses the criterion's real name.

### 2026-06-14 — Faster chatbot

- The chat assistant now runs on a faster configuration: `gpt-5-mini` (new
  `openai_chat_model` setting) with `reasoning_effort=low` and **web search off** for chat
  turns — the tools and the injected briefing already carry the data it needs (`gpt-5`
  stays for research/scoring). `create_with_tools` gained `model`/`reasoning_effort`
  params; `AIQueryLog` now records the actual model per call. Measured: plain reply
  ~18s→~9s, tool-action turn ~40-55s→~12s.

### 2026-06-14 — Social criteria, onboarding-to-table, user-defined criteria

First user feedback, top priority. Three workstreams:

- **Tolerance & inclusion, gender equality, cultural life, food culture** are now scored
  criteria. Onboarding asks (optionally, privately) which communities' acceptance matters
  to the user (LGBTQ+, Jewish, Muslim/Arab, Black & ethnic minorities, immigrants); a
  country's inclusion score is the **worst-accepted** of those communities (a place hostile
  to even one doesn't look safe), falling back to general openness when none are named.
  New leaving-reason "discrimination" up-weights inclusion. New "Only welcoming places"
  filter. Per-country social data is AI-assessed (anchored on ILGA, Global Gender Gap
  Index, discrimination/integration reports) — schema in `place_research`, backfilled onto
  the seeded set via `./xcape.sh backfill-social`. Profile field `minority_groups`
  (migration 0010), scored in `shortlist` (worst-group rule, neutral when data missing).
- **Onboarding goes straight to the comparison table** (pre-filled with the top 5 matches);
  the old country-checklist step is gone (`/shortlist` redirects to `/compare`). A
  "Suggested matches" strip one-click-adds the rest of the ranked pool.
- **User-defined criteria**: add any criterion (panel or chat, e.g. "vegan-friendly") and
  the AI rates each country good/ok/bad with a justification; it joins the ranking like a
  built-in. Shared per-(country, criterion) cache `place_custom_evals` +
  `searches.custom_criteria` (migration 0011); new `services/custom_criteria.py`, endpoint
  `POST /searches/{id}/custom-criteria`, and chat tool `add_custom_criterion`.

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
