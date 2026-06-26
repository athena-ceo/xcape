<!-- Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

# Changelog

## [Unreleased]

### 2026-06-26 — Home country excluded from candidates

- The user's current country is the comparison **baseline** only — it never appears as a
  destination candidate (true for any country, e.g. France for a France-based user). Centralised
  the candidate-country pool behind `_candidate_countries()` in `shortlist.py`, which all four
  ranking paths (instant shortlist, repopulate, explore, wildcards) now use, and rejected adding
  the home country via the API (`POST …/candidates` → 400). The picker also hides the baseline.
  Existing boards drop a stray home-country row on the next "Refresh list" (repopulate).

### 2026-06-25 — Drill-down currency converter

- When a country's currency differs from the user's, the drill-down shows a small **two-way
  converter** (type in either currency, see the other). The `GET /places/{id}/facts` response
  carries a per-user `fx` block (local currency, user currency, and the local-per-user rate via
  the existing EUR-based FX); the converter is hidden when the currencies match.

### 2026-06-25 — Visa finder integrated into the country search (as scored criteria)

The golden-visa finder is now optionally part of the ranking, not just a standalone page.

- **Two new optional profile fields** — `annual_income` and `investable_amount` (migration `0026`),
  captured in onboarding (budget step) and the profile, in the user's currency.
- **Two new computed criteria** — *"Residency on your income"* and *"Residency by investment"* —
  scored deterministically (no AI) per country from the user's figures vs the cached visa
  thresholds: clears the easiest qualifying route → good, a route exists but is out of reach → ok,
  no monetary route → weak. Compared in canonical **EUR** (currency-neutral) via the same finder
  data, threaded through the scoring pipeline as augmented `evals`.
- **Kept separate, by design** — investment vs income are different answers depending on financial
  status, so they're two criteria, not one.
- **Activate on entry** — providing a figure turns its criterion on at high importance; clearing it
  makes it dormant (weight 0 → hidden). If neither is given, nothing changes and the standalone
  Visa finder still works.
- Rollout note: the new criteria need the registry — run `./xcape.sh reseed <env> --criteria` after deploy.

### 2026-06-25 — Real-estate ↔ visa tie-in (Phase 3) + multi-currency sweep

- **Real-estate tie-in (golden-visa Phase 3)**: the budget panel now shows, when a country has an
  investment route, "buying a home here may count toward the {program} — residency by investment
  from {amount}", tying the property cost to the golden-visa threshold. Built entirely over the
  structured EUR threshold, converted to the viewer's currency — currency-neutral by construction.
- **Multi-currency sweep**: confirmed all monetary data is cached in canonical **EUR** and converted
  to each *viewing* user's currency at read time (shared cross-user caches never bake in the
  generating user's currency). Fixed the one real leak: **AI narrative was embedding currency
  amounts** (the cost breakdown's notes/summary asked the model to "state the assumed price" and
  showed "≈ 3 060 €" even for a USD viewer, contradicting the converted cells). The cost and visa
  prompts now forbid monetary amounts/symbols in prose — money lives only in the structured,
  convertible fields. Cost prompt version bumped so existing rows self-heal on next view; the visa
  change applies to future generations (the seeded finder thresholds already convert correctly).

### 2026-06-25 — Data pipeline consolidated: one `generate`, one `reseed`

Nine overlapping db commands collapsed into two over a shared generator abstraction:

- **`./xcape.sh generate [--only attributes,criteria,visas,cost] [--force] [--limit N] [--check]
  [--export]`** — one command fills all shared AI-derived country data, cache-first, resumable,
  Ctrl-C-safe. Each data kind is one entry in a generator registry (find what's missing/stale +
  fill one cell); a single driver loops them. `--check` reports pending work with no AI calls;
  `--export` snapshots the caches to the git seed — now including **place attributes** (which never
  round-tripped before), so generate-on-dev → reseed-on-prod carries everything.
  Replaces: `evaluate-all`, `evaluate-visas`, `backfill-social`, `backfill-living`, `regen-text`,
  `export-evals`, `verify-evals`.
- **`./xcape.sh reseed <env> [--criteria]`** — load the committed seed (places + attributes +
  evals), overwrite; `--criteria` also rolls the registry. Replaces `reseed-data` + `reseed-criteria`.
- Most of this data also **self-heals on view**, so `generate` is a warm-up / finder-prep, not a
  requirement. Cheaper model (`gpt-5-mini`) now used for on-demand country research and the batch
  attribute fill.

### 2026-06-25 — Self-healing attributes, duplicate-country fix, graceful Ctrl-C

- **English/tax-basis now self-heal on demand** instead of needing a bulk backfill: the drill-down's
  generate path fills `english` (Language criterion) and `tax_basis` (budget panel) on first view via
  the existing single-attribute filler — so only countries someone actually opens cost an AI call,
  once. `backfill-living` is now an *optional* warm-up, not a requirement. (Most countries are never
  visited, so bulk pre-computing AI across all ~218 is wasteful.)
- **No more duplicate countries**: on-demand research now dedupes by **ISO code**, so searching
  "Spain" when the DB already has "Espagne" (both ES) reuses the existing row instead of creating a
  second. New `./xcape.sh dedupe-places [--dry-run]` merges any existing ISO duplicates (keeps the
  canonical row, moves board entries onto it, deletes the rest).
- **Ctrl-C is graceful**: the long-running db scripts (backfill-living/social, evaluate-visas,
  evaluate-all, regen-text) now catch the interrupt and print "progress saved (resumable)" instead of
  dumping a traceback — they already commit incrementally.

### 2026-06-25 — Ancestry & heritage right-of-return pathways

Heritage-based immigration was under-covered: the ancestry route only surfaced when the
destination's ISO was in the user's declared ancestry countries — fine for Ireland/Italy by
descent, but it missed ethno-religious **right-of-return** laws (Israel's Law of Return is based
on Jewish heritage, not Israeli ancestry).

- **New "heritage" question** (onboarding + profile): declare a heritage that may grant a right of
  return independent of a country of ancestry (Jewish to start; `users.heritages`, migration `0025`).
- **Surfaces the routes**: a Jewish-heritage user now sees the ancestry/heritage pathway for Israel,
  Germany (Art. 116) and Spain/Portugal (Sephardic). The AI eval describes the *actual* conditions,
  including where a route is restricted or closed — it's a surfacing hint; eligibility is the user's
  to confirm. The category is relabelled "Ancestry / heritage".
- **Richer eval**: the ancestry/heritage prompt now covers descent (jus sanguinis, eligible
  generation, foreign-births registration, documentation) AND right-of-return laws. Invalidated
  surgically per-category (only ancestry rows regenerate — the investment/retirement/nomad finder
  cache is untouched).
- **Ranking**: a strong, open heritage route (Jewish → Israel's Law of Return) boosts the
  "ease of settling (visa)" score like a declared ancestry tie; restricted routes don't.

### 2026-06-24 — Smarter post-login routing + resumable onboarding

- **Login lands where it should**: a returning user who already has a completed search goes
  straight to their **comparison board** (`/compare/{latest}`) instead of back through onboarding;
  a user with no search goes to onboarding.
- **Onboarding resumes where you left off**: the wizard now saves an in-progress **draft** (current
  step + all answers + chosen persona) to the browser as you go, and restores it on return — no
  re-entering everything. The draft is cleared when onboarding finishes, on "New request" (start
  over), and on logout (so it never leaks to the next user on a shared browser). Pressing Enter on
  the login password also submits now (separate fix).

### 2026-06-24 — Comparison board: roomier table, wrapping criterion column, neutral pending

- **Wider board on desktop** (`max-w-4xl` → `max-w-7xl`) so country columns use the available width
  instead of crowding into a narrow strip.
- **Criterion column no longer hogs space**: it was `truncate` + `max-w-none`, so on desktop the
  column stretched to fit the longest criterion name on a single line. It's now a fixed, narrow
  width (`w-32` mobile / `w-64` desktop) with long names **wrapping to multiple lines** — works on
  both phone and desktop.
- **Category roll-up values are now underlined** (dotted) like criterion values, so it's clear they
  open the country drill-down.
- **Just-added custom criteria read neutral, not "Weak"**: a not-yet-evaluated leaf is excluded
  from its category roll-up until its evaluation lands, so "Your criteria" shows "—" (neutral)
  instead of an unearned "Weak" while the AI is still working.

### 2026-06-24 — Admin: regenerate a country's data from the Places list

- **Per-country "↻ Regenerate" action** in the admin Places list (one per country) — for when a
  country is reported outdated or incorrect. It opens that country's drill-down and auto-runs the
  existing full force-regenerate (every criterion's score + text, all visa pathways, the budget
  breakdown), so the admin watches it refill live and can verify the corrected data and sources.
  Reuses the drill-down's incremental regenerate (`?regen=1` deep-link); the force endpoints stay
  admin-gated server-side.

### 2026-06-24 — Golden-visa finder (Phase 2): "I have €X — where can I go?"

A standalone **Visa finder** page (top-nav link) that inverts the per-country drill-down:
enter an amount and a goal, get the countries it opens a residency route to, ranked.

- **Two goals**: *a lump-sum investment* (ranked on each country's investment / golden-visa
  threshold) or *passive / pension income* (ranked on the retirement & digital-nomad annual
  income thresholds) — covering both the NYT golden-visa and *International Living* audiences.
- **Ranking**: easiest-first (accessibility), then least time committed on the ground (minimum
  stay, then years to citizenship). Each result shows the program name, threshold, stay and
  PR/citizenship timeline, and deep-links into the country drill-down.
- **Amount is in the user's budgeting currency**, converted to the canonical EUR thresholds
  server-side; results come back converted for display.
- **Backend**: `GET /visa/finder?amount=&goal=&lang=` over the shared pathway cache (no AI on
  the request path). New `./xcape.sh evaluate-visas` pre-computes the investment / retirement /
  digital-nomad pathways for every country so the finder can rank across all of them
  (cache-first/resumable).

### 2026-06-24 — Admin: full user management + richer AI log

- **User management.** The admin Users tab can now **add** an account (inline form), **change
  password**, **reset data**, **disable/enable** (soft — blocks login, keeps data, reversible),
  and **permanently remove** (hard delete, guarded by typed-email confirmation). The list now shows
  **last login** and **latest search** (title + date), and a *disabled* badge.
  - Backend: `POST /admin/users`, `PATCH /admin/users/{id}/active`, `DELETE /admin/users/{id}`
    (guards: can't disable/delete yourself, can't delete the last admin). New `users.is_active`
    column (migration `0023`); login and `get_current_user` reject disabled accounts (403).
- **Two overlapping reset labels fixed.** The password button read just "Reset" next to "Reset
  data"; it's now "Change password" so the two actions are unambiguous.
- **AI log shows who/what/result.** Each AI call now records a **result summary** (the return value,
  migration `0024` — `ai_query_logs.result_summary`) alongside the existing request summary, and the
  log surfaces the **triggering user's email**. The admin AI tab is now a one-line-per-call view
  (user · kind · model · request · result) with an expandable panel for the full request/result and
  token/latency diagnostics — modelled on golden-path's activity log.
- Tests: create/duplicate, disable→login-blocked→re-enable, delete + self/last-admin guards, users
  list fields, AI-log user/summaries.
- **Token usage & estimated cost per user.** The Users tab now shows each account's **AI calls**,
  **total input/output tokens**, and an **estimated USD cost**, so spend can be gauged per user;
  each AI-log call also shows its own estimated cost. Cost comes from a small editable price table
  (`services/pricing.py`, USD per 1M tokens by model) computed on read — never persisted — so a
  price correction applies to the whole history. Per-user totals aggregate by model so each model's
  rate applies. Update `MODEL_PRICING` when provider prices change.

### 2026-06-23 — Lodging cost is bedroom-aware; criteria sort by importance; mobile voice diagnostics

- **Housing scales by bedrooms, not a flat per-head factor.** The affordability calculator now sizes
  the home by the bedrooms a household needs — one for the primary occupant or couple, plus one per
  additional member (typically children): 1–2 people → 1 BR, 3 → 2 BR, 4 → 3 BR. Each extra bedroom
  adds ~50% of a one-bedroom's cost (a 3-bed ≈ 2× a 1-bed). A couple now pays the same housing as a
  single person instead of an unexplained 1.35×. The housing breakdown row shows the bedroom count
  it was sized for. (`affordability.housing_factor` / `bedrooms_for_size`; non-housing components
  keep their per-head marginals.)
- **Comparison criteria sort by importance by default** (was category), so the most-weighted criteria
  are at the top on first load.
- **Voice input fixed on iPhones.** `MediaRecorder` was started with a 1s timeslice; on iOS Safari
  that emits fragmented mp4 chunks that don't reassemble into a decodable file (the combined Blob
  has no moov atom), so the upload transcribed to nothing. Now recorded without a timeslice — a
  single finalised file every browser (incl. iOS) can decode. Also hardened the failure paths:
  distinct messages for an insecure (non-https) origin, an unsupported browser, and a denied mic
  permission, plus the real `getUserMedia` error name logged for diagnosis.

### 2026-06-23 — Cost-of-living scoring no longer over-eliminates on a generous budget

- **Affordability recalibrated.** A generous budget (e.g. €4000/mo) was eliminating most desirable
  countries, especially for couples/families. Two causes fixed in `shortlist._cost_value`:
  - The flat household multiplier (×1.6 couple, ×2.4 family) was applied to the *whole* basket,
    including rent — but housing is largely shared. Softened to ×1.35 / ×1.9 (unknown → ×1.25),
    matching the per-component model the affordability drill-down already uses.
  - The score floored to 0 (eliminated) once budget covered <50% of the estimate. Lowered to 40%,
    so only a genuine 2.5× shortfall zeroes a country; a budget that merely trims the surplus
    still scores well.
- **Cost bands re-bucketed.** 12 mid-cost countries were miscategorised as `high` cost and lumped
  with Switzerland/Monaco/Norway at the same €3500 single-person estimate: Bulgaria, Croatia,
  Czechia, Estonia, Hungary, Latvia, Lithuania, Poland, Romania, Slovak Republic, Slovenia, and the
  Russian Federation moved `high → medium` in `places_seed.json`. Apply to an existing DB with
  `./xcape.sh reseed-data <env>`.
- Regression test added: a family on €4000 is no longer eliminated from mid-cost countries, while a
  genuinely expensive country still reads as a stretch (low but non-zero).

### 2026-06-23 — Comparison table readable on narrow phones (portrait)

- **Compact mobile layout for the comparison table.** The frozen criterion-name column was so wide
  on a portrait phone that no country columns were visible. On mobile the sticky column is now
  width-capped (≤34vw) with truncated labels, cell padding is reduced, and country headers shrink,
  so at least two country columns sit alongside the criterion column; the full-size table is
  unchanged from `sm` upward.

### 2026-06-23 — Immigration pathway bullets respect the UI language

- **Mixed FR/EN in pathway cards fixed**: the requirement bullets on each immigration-pathway card
  (e.g. "Valid job offer…", "Clean criminal record…") were stored as a single language-agnostic
  `requirements` array and rendered verbatim, so in French mode the card's heading and summary were
  French but the bullets stayed English. The model now returns `requirements_fr` / `requirements_en`
  (same bullets, both languages), the payload carries both, and the drill-down picks the array that
  matches the active language (falling back to the other if one is empty). `VISA_PROMPT_VERSION`
  bumped to `2` so cached cards re-evaluate bilingually the next time a place is opened.

### 2026-06-24 — Golden-visa / retiree features (Phase 1): residency at a glance

Aimed at the audiences in the NYT golden-visa coverage and *International Living* — affluent
"Plan B" buyers and retirees. Adds the structured facts those readers actually compare on:

- **Minimum stay per year**: each visa pathway now carries `min_stay_days` — the "do I actually
  have to live there" figure (e.g. Greece none, Costa Rica ~1 day, Portugal ~7 days) — shown on
  the pathway card.
- **Named programs**: pathways carry the official program name (D7, Pensionado, Golden Visa…)
  shown beside the category.
- **English at a glance**: a new `english` country attribute (widely / moderate / limited) shown
  on the Language criterion — what a monolingual newcomer most wants to know.
- **Tax basis + US-person note**: a new `tax_basis` attribute (territorial / worldwide / hybrid)
  in the budget panel, plus an origin-aware reminder that US citizens are taxed on worldwide
  income wherever they live (framed clearly as informational, not tax advice).
- **Ops**: `./xcape.sh backfill-living` AI-fills `english` + `tax_basis` on seeded countries;
  the visa prompt version bump means `./xcape.sh regen-text` refreshes pathways with the new
  fields.

### 2026-06-24 — Consistent localization: bilingual drill-down text + localized custom labels

- **Drill-down language consistency**: two cached AI fields were generated in a single language
  (usually English) while the surrounding text was French — the **visa requirement bullets** and the
  trend-lens **"evidence" line** (under Sécurité, Stabilité politique, per-community safety…). Both
  are now generated bilingually (`requirements_fr/_en`, `metric_fr/_en`); the API resolves each to
  the UI language so the page reads them unchanged.
- **Surgical cache invalidation**: a new per-lens `LENS_VERSION` lets us invalidate only the trend
  rows (not all ~190× evals); the visa prompt version was bumped. Legacy single-language rows still
  display (fallback) until regenerated.
- **Custom-criterion labels are localized**: user-added criteria stored only the raw text the user
  typed, so the comparison table / drill-down showed it untranslated in the other language. New
  criteria now get `label_fr`/`label_en` (a short AI translation at creation); persona criteria use
  their registry labels. `labelOf` picks the active-language label everywhere.
- **`./xcape.sh regen-text`**: regenerates the version-stale drill-down text (trend evidence + visa
  bullets) and backfills `label_fr`/`label_en` onto existing custom criteria. Cache-first and
  resumable (`--force`, `--no-text`, `--no-labels`).

### 2026-06-22 — Comparison table polish + chat: home country isn't a candidate

- **Sticky first column**: the criterion-name column now stays pinned while you scroll the country
  columns horizontally (each first cell pinned with an opaque background), so on mobile you never
  lose track of which row is which.
- **Consistent value type scale**: the category rollup values were `text-xs` while criterion values
  and category labels were `text-sm`, making category labels look oversized. All value words are
  now `text-sm`; category labels keep a subtle bold emphasis.
- **Chat — home country is the baseline, not a destination**: the assistant used to offer to "add
  France to your shortlist" when France is the user's home country. The prompt now states the
  country of residence is the comparison BASELINE, never a candidate to add — it may still
  recommend *staying put*, framed as such.

### 2026-06-22 — Add-country affordance, home-country explanation, weight spread, proximity

- **Add a country from the board**: a "+" affordance in the comparison table header opens a modal
  to search/add a country — no need to detour through the full "All countries" list. When the board
  is full it reuses the **same "replace the weakest" pruning** as the Explore list (extracted into a
  shared `services/board.ts` helper — not duplicated).
- **Home-country score is now explainable**: the baseline (current-country) column's score opens the
  same per-criterion breakdown as candidates. Backend `explain_candidate` refactored into
  `explain_place(place, search)` with a new `GET /searches/{id}/baseline/explanation`.
- **Bigger distinction between criteria**: persona weights were rescaled so the high/"élevée" tier
  (was 2.5–3) reaches **5–6** while low/contextual tiers stay put — widening the high-to-low ratio
  so criteria you care about dominate (a weighted *average* is invariant to uniform scaling, so only
  the ratio matters). The importance stepper cap is raised 5 → 8.
- **Proximity** (distance to your home country) now carries a modest weight in **every persona**
  (was 0 everywhere, so it never counted). Confirmed it's computed **per-user** from the current
  country and never cached cross-user — no contamination by the first user's home country.
- NOTE: the persona/registry change lives in the DB (`app_config['criteria']`); run
  `./xcape.sh reseed-criteria <env>` to roll it out (done for dev).

### 2026-06-22 — Mobile: comparison table no longer clipped off-screen

- On phones the comparison board (and the header nav) ran off the right edge with no way to reach
  the cut-off columns. Cause: the non-wrapping header nav was wider than the viewport, and with no
  `overflow-x` guard that widened iOS Safari's layout viewport — inflating the centered `max-w-3xl`
  content so the wide table was pushed partly off-screen (its own inner scroll couldn't help,
  because its container was off-screen too).
- Fix: `overflow-x-hidden` on the app shell so no single wide element widens the page, and the
  header nav now **wraps** instead of overflowing. The comparison table keeps its own inner
  horizontal scroll, so all country columns are reachable by swiping the table.

### 2026-06-22 — Explore: always show excluded; add-to-board when full replaces the weakest

- Removed the **"Show excluded" toggle** — excluded countries are now always listed (each still
  carries its inline "doesn't match" warning), so nothing is hidden behind a checkbox.
- **Add-to-board no longer fails silently when the board is full.** Previously the country was added
  to the pool but left off the board (board caps at 5), with no feedback. Now, if the board is full,
  it asks to **replace the lowest-ranked member** (named, with its score) and on confirm swaps it in
  — the board stays at 5. New `evict_place_id` on the add-candidate endpoint de-selects the chosen
  member (clearing its pin) before adding; the explore list refetches so membership stays accurate.

### 2026-06-22 — Criteria registry: self-healing load (fixes blank personas / labels)

- A single transient `GET /criteria` failure (cold start, dropped request, brief token gap) used
  to **blank the entire registry-driven UI for the whole session** — no personas in onboarding, no
  criterion labels/categories — because `loadCriteria` cached the *rejected* promise and returned
  it to every later caller, and `useCriteria` swallowed the error and never retried.
- `loadCriteria` now clears its cache on failure (re-fetchable) and `useCriteria` **retries with
  capped exponential backoff** (1s→15s) until the registry loads, so the UI self-heals without a
  manual reload — important on mobile where reloading isn't easy.
- Central guard: `labelOf` (the single function every criterion label flows through — board, score
  popup, drill-down, profile, explore) now falls back to a **humanized key** ("cost_of_living" →
  "Cost of living") instead of exposing the raw slug while the registry loads. No more per-screen
  patches — the onboarding persona step keeps a loading spinner only because its *list* is empty
  (nothing to label) until the registry arrives.

### 2026-06-22 — Per-user budgeting currency

- **Budgeting is no longer euro-only.** Added `profile.currency` (ISO-4217), editable in the
  profile, with a per-currency selector next to the budget. When the user hasn't chosen one it's
  **derived from their country of residence** (e.g. US → USD, UK → GBP; eurozone → EUR) and
  persisted so scoring can read it.
- The shared country data (cost breakdown, visa income/investment thresholds) stays **canonical in
  EUR**; every money figure is **converted to the user's currency at the boundary** for display,
  and the budget is converted back to EUR to stay comparable across users in the cost-of-living
  ranking. The drill-down budget calculator, the cost breakdown + per-entry popup, the visa income
  tie-in, and the visa-pathway cards now all show money in the user's currency (locale-aware symbol).
- Exchange rates: new `services/fx.py` fetches EUR-based ECB reference rates once per day
  (Frankfurter, keyless), cached in-process, with a built-in fallback table so budgeting never
  breaks offline. Country → currency mapping in `services/currencies.py`.
- Migration `0022_profile_currency`. Tests: `test_currencies.py`, currency conversion + profile
  default/override in `test_affordability.py` / `test_profile.py`.

### 2026-06-22 — Budget / affordability calculator on the drill-down

- New **budget & affordability calculator** on the country drill-down — a **collapsed-by-default,
  lazily-loaded panel** (no fetch or AI cost-breakdown generation until the user expands it; the
  open/closed choice is remembered). Inside: editable monthly budget (prefilled from the profile)
  and household size, an AI-estimated per-country monthly cost breakdown (rent / utilities / food /
  healthcare / transport / other) scaled to the household, and an **estimated cost vs budget**
  verdict (comfortable / manageable / tight / insufficient) with surplus/deficit and a coverage bar.
  Each breakdown entry is **clickable for a "how this is estimated" popup** — the AI returns a
  per-component FR/EN justification, shown alongside the per-person base and the household scaling.
- **Housing follows the user's tenure**: the breakdown caches both a monthly **rent** and a monthly
  **mortgage** (buy) figure, and shows the mortgage for users who said they want to buy (rent
  otherwise) — no more estimating rent for a buyer. The two figures share one user-neutral cache;
  tenure just selects which to display.
- The drill-down's **visa-pathways panel is now collapsible and lazy** too (collapsed by default,
  open/closed remembered) — matching the budget calculator, so neither generates AI content until
  the user expands it. The admin regenerate still force-refreshes both even while collapsed.
- The admin **"Regenerate text"** button moved to the **top of the drill-down** and now re-researches
  **everything** for the country in one action — every criterion's detail text, the visa pathways,
  and the budget cost breakdown (forced regardless of cache). The visa-pathways and affordability
  generate routes gained an admin-only `force` flag for this.
- **Cost breakdown** is generated on-demand and cached in `place_custom_evals` under
  `key = "cost_breakdown"` (versioned `prompt_fp`, shared cross-user) — same pattern as the
  objective evals and the visa catalog, so no schema change.
- **Visa income tie-in**: annualised income (budget × 12) is compared against the cached visa
  pathways' `income_eur` thresholds to flag which income-based routes (retirement, digital nomad)
  the income qualifies for.
- New auth'd routes `GET/POST /places/{id}/affordability[/generate]`; service
  `app/services/affordability.py`; tests in `tests/test_affordability.py`.

### 2026-06-16 — evaluate-all covers bucket-only cells by default

- `evaluate-all` now evaluates every (country, criterion) cell — including those relying only on
  a coarse seed bucket — by **default**, so a plain run always closes the gap (e.g. a
  low-default-weight criterion like education that was never lazily evaluated, which left a
  version-bump regeneration ~189 short). `--skip-buckets` opts into the cheaper gap-fill-only
  mode; `--include-buckets` is now the default (kept as a no-op for back-compat).

### 2026-06-16 — Discoverable category expand + inline criterion filters

- **Categories read as expandable**: a boxed ▸/▾ chevron, a row hover state, and a "N · open"
  cue on collapsed categories — so it's clear you open one to see (and tune) its criteria.
- **Filter criteria inline**, the analog of the inline weight stepper: each criterion row has an
  Any / ≥ OK / ≥ Good filter selector (built-ins set a profile filter, custom criteria set their
  per-search min; both re-rank immediately). Bespoke filters (climate/visa/language/inclusion)
  stay in Criteria settings. The interaction hint now mentions opening categories.

### 2026-06-16 — Onboarding: pick a persona directly (no guessing)

- Onboarding now **leads with a persona picker** — a list of profiles with their descriptions
  and focus criteria, chosen directly — instead of inferring one from "Why are you leaving?" +
  "What matters most?". Those two steps are removed; the chosen persona sets the starting
  weights and default filters, and only its relevant follow-ups (communities, budget, climate)
  are then asked, plus the optional free-text. A returning user's saved persona is pre-selected.
  Fewer, clearer screens; no opaque guessing (which had mis-classified some users).

### 2026-06-16 — Remove "Tune by situation" from the board (declutter)

- Dropped the "Tune by situation" button/panel from the comparison board. Its function (AI
  guessing weights/criteria from tags + free text) overlapped the persona (situation→weights at
  onboarding), the onboarding free-text step, and the chat — adding an opaque, redundant control.
  The underlying `suggestCriteria` endpoint stays (onboarding free-text still uses it); explicit
  tuning lives in Criteria settings / inline steppers, and free-text refinement in the chat.

### 2026-06-16 — Smoke test self-cleans; prod-safe test-user purge

- The deploy **smoke test now deletes its throwaway account** at the end (new self-service
  `DELETE /auth/me`, cascades the account's data), so `smoke-*@example.com` users no longer
  accumulate on prod.
- `./xcape.sh purge-test-users <env>` is now **allowed on prod** (was refused) behind a
  confirmation — scoped strictly to `@example.com` / `@xcape.test`, so it can clear the existing
  backlog without ever touching real users.

### 2026-06-16 — Admin: hide test/smoke accounts from the Searches log

- The Admin → Searches log now **excludes test/automation accounts by default** — the smoke
  test registers a `smoke-*@example.com` user (with a search) on every `deploy prod`, and dev
  scripts use `@example.com` / `@xcape.test`. A **"Show test accounts"** checkbox reveals them;
  rows are tagged `is_test`. `GET /admin/searches?include_test=true` opts in.

### 2026-06-16 — Admin: set a persona's default filters

- The Admin → Personas editor now has a **"Default filters"** section (a checkbox per criterion)
  to choose which criteria a persona auto-applies as exclude-"À éviter" hard filters — the
  `persona.filters` list that was only editable by hand-editing criteria.json. `PUT /admin/criteria`
  validates that filter keys resolve to real criteria, like weights.

### 2026-06-16 — Community-safety criteria stay under Safety & protection

- Per-community safety criteria (e.g. "Safety for my community — …") now reliably group under
  **Safety & protection** in both the comparison board and the drill-down, not under "Your
  criteria". Newer ones already carried `category: protection`; **older stored defs lacking it
  are now self-healed on read** (`custom_criteria.heal_categories`), so existing searches fix
  themselves.

### 2026-06-16 — Fix never-ending spinner; board sort + proximity criterion

- **Hung "Recherche…" spinner fixed.** The progressive-fill loop only stopped when nothing was
  pending; a cell that couldn't be evaluated (AI failure / unresolvable) kept it spinning for
  up to 200 slow rounds. Added a no-progress guard: if a round clears nothing, it stops (the
  cell is retried on the next action).
- **Sort criteria by importance.** The comparison table has a "Sort: by category / by
  importance" control; importance floats the heaviest categories and criteria to the top.
- **Proximity to country of origin** is now a selectable proposed criterion in onboarding and
  the profile (it was a hidden computed criterion).

### 2026-06-16 — Robust AI JSON parsing (long jobs survive a bad reply)

- `ai_client.respond_json` no longer crashes on a truncated/invalid model response: it retries
  once and, if still unparseable, raises `AIUnavailable` so callers degrade gracefully (e.g.
  `evaluate-all` skips that cell and continues, picking it up on the next resumable run). A
  single malformed reply previously killed the whole population job.

### 2026-06-16 — Explore Phase 2: wildcards (idea sparks)

- The Explore view now shows a clearly-labelled **"✨ Sparks"** strip — a few off-board
  **dark-horse** countries (not recommendations): countries you don't already see that
  genuinely excel on a criterion you weight (standout ≥ 70), with a non-terrible overall fit.
  Each card shows "Strong on {criterion}" + score and links to the drill-down; a **Shuffle**
  control reshuffles. `GET /searches/{id}/wildcards`.

### 2026-06-16 — Explore: full ranked country list (also the mobile results view)

- New **Explore** route (`/explore/:searchId`, reached via "Explore all countries" below the
  board): a read-only ranked list of EVERY country against your current weights/filters —
  name + match score + short reasons, text-filter + sort (best match / name), add-to-board and
  drill-down per row. Filter-passing by default with a "Show excluded (N)" toggle that lists
  violators with the localized reason. Doubles as the mobile-friendly results view (a list, not
  a wide matrix). New `GET /searches/{id}/explore` (rank_all) — read-only, no board mutation.

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
