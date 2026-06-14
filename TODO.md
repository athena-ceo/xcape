<!-- Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

# xCape — backlog

Deferred work. Each item notes what "done" looks like, why it matters, and the files
affected. Ship items independently.

## Open

### Admin management of all reference data (open-set defaults)

**Principle:** every enumerable dimension is an *initial seed*, not a closed set — admins
must be able to **add / remove / modify** the defaults of each class at runtime, and the
additions are first-class everywhere (scoring, evaluation, display, filtering). Classes:
criteria (nodes/leaves), categories, tags, personas, reasons-for-leaving, communities — and
the **places** themselves (countries / regions / cities) with their attributes.

**Done looks like:** an admin section to CRUD each class, persisted so changes take effect
without a deploy.

**Approach:** the registry already reads through one loader (`services/criteria.py
_registry()`) and places are already in Postgres, so:
- Move the criteria registry from the bundled `app/data/criteria.json` into **DB tables**,
  **seeded idempotently from the JSON** (mirror `app/db/seed.py`); point the loader at the
  DB (JSON becomes the seed, not the source). Add admin endpoints + UI to CRUD them, and
  invalidate the loader cache on edit.
- Add admin CRUD for **places/regions/cities** + their attributes (places are already a DB
  table; the admin list is currently read-only — make it editable, support regions/cities
  via the existing `kind`/`parent_id`).
- Guard with `require_admin`; validate (e.g. don't delete an in-use criterion without
  reassigning).

**Why:** the sponsor wants to shape the catalog (persona criteria, tags, country data)
without code changes; natural home for the persona/criteria content work.

**Files:** `services/criteria.py` (loader → DB), new models + migration + seeder,
`api/v1/admin.py` (+ criteria/places admin routers), `src/pages/AdminDashboard.tsx`, i18n.
The frontend reads the catalog via `GET /criteria` (P2b), so it reflects admin edits.

### Employment, retirement & cross-border taxation criteria

**Idea:** a whole category of work/money-mobility criteria that strongly drive relocation
but aren't captured yet:
- **Job opportunities** — demand in the user's field/occupation, overall unemployment,
  job security, ease of getting hired given the user's **language level** (ties into
  `language_ease`), work-visa/permit ease for their citizenship (ties into `visa`).
- **Employer presence** — whether the user's current employer (esp. multinationals) has
  offices there → a concrete pull. Capture employer name → office locations via search.
- **Retirement** — many users relocate to retire: pension/retirement-visa options for
  **non-local** workers, cost & taxation of retirement income, healthcare access for
  retirees, residency-by-means routes (e.g. Portugal D7). Make this a first-class
  user situation (a "retiring" mode/household state), not just a job angle.
- **Cross-border taxation penalties** — double-taxation exposure based on the user's
  **citizenship(s) + current country + destination**: is there a tax treaty? (e.g. the
  US↔France treaty avoids double *taxation* but not double *filing*; US↔Saudi Arabia has
  none). Also exit taxes, wealth tax, taxation of foreign/retirement income, social-charge
  treaties. This is inherently per-user (depends on citizenship), like visa/inclusion.

**Done looks like:** new built-in criteria (e.g. `jobs`, `employer_presence`,
`retirement`, `tax_treaty`) scored against the profile, with the user-specific ones
(tax treaty, work-permit, employer) computed from citizenship + employer inputs and
explained in the drill-down; new onboarding inputs (occupation/field, current employer,
"retiring?" flag). Some of these (tax-treaty matrix, employer offices) are best AI-/data-
backed and cached per (citizenship × destination) or (employer × country), mirroring the
custom-criteria cache.

**Approach:** start with the two highest-value, most-tractable pieces —
(1) a **tax-treaty / double-taxation** signal keyed on citizenship+destination (AI lookup
+ cache, surfaced under the existing `tax`/`visa` story), and (2) **job opportunity by
field + language**, reusing the custom-criteria evaluation machinery
(`services/custom_criteria.py`). Retirement and employer-presence follow. Needs design for
the new profile inputs and the per-user caching key.

**Why:** income, retirement security and tax exposure are decisive for real moves and a
strong differentiator; "I'd be double-taxed there" can rule a country out entirely.

**Files:** `data/profileOptions.ts` + onboarding/profile (occupation, employer, retiring
flag, citizenship already present), `services/shortlist.py` (new criteria + per-user
scoring like visa/inclusion), `services/place_research.py` or a new service + cache table
for tax-treaty/employer data, `models/profile.py` + migration, i18n,
`docs/xcape-design-and-criteria.md`.

### Voice output for the chatbot (text-to-speech)

**Now:** voice **input** exists (`src/components/VoiceButton.tsx` records audio →
`/voice/transcribe` → `ai_client.transcribe_audio`, `gpt-4o-mini-transcribe`), but the
assistant only replies in text. The loop is one-way.

**Done looks like:** the chatbot's replies can be **spoken back** in the user's locale
(FR default / EN), with a per-message play/stop control and an optional auto-speak toggle.
Voice-in → voice-out makes the assistant usable hands-free / on mobile.

**Approach options:**
- OpenAI TTS (`gpt-4o-mini-tts` / `tts-1`) via a new `/voice/speak` endpoint that returns
  audio for a given text + locale; play it client-side with an `<audio>` element. Cache by
  text hash to avoid re-synthesising identical replies; log under `AIQueryLog` kind=`voice`.
- Or the browser's built-in `speechSynthesis` (Web Speech API) — zero backend, zero cost,
  but voice quality and FR support vary by browser/OS.
- Stream the audio if latency is an issue; otherwise synthesise the whole reply.

**Why:** symmetry with voice input; accessibility and a more natural, hands-free chat.

**Files:** `services/ai_client.py` (a `synthesize_speech` helper) + `api/v1/voice.py`
(`/speak`), a frontend speak control on chat bubbles in
`src/pages/ComparisonPlayground.tsx` (reuse/extend `VoiceButton.tsx`), `src/services/api.ts`,
i18n, `models/ai_log.py` kind already lists `voice`.

### International schools in the education research

**Done looks like:** when education matters (family / couple-with-kids), the research
surfaces international / bilingual schools appropriate for the family's **languages and
nationality** (e.g. French schools abroad — AEFE network, IB schools, American schools),
with locations. This is **user-specific** (depends on their languages/citizenship), so it
can't live in the shared per-place cache as-is — likely a per-user/per-search detail or a
chat-driven lookup. School availability also feeds the region/city stage and the detailed
cost of living (tuition).

**Why:** for families, access to the right school often decides the city, not just the
country.

**Files:** `services/place_research.py` (education detail), a per-user detail path,
region stage, cost breakdown.

### Detailed, editable cost-of-living breakdown (own section)

**Now:** cost of living is one symbolic level scored against a budget band (coarse). The
seed value for auto-generated countries is derived from World Bank income tier, which is
often wrong (e.g. Slovenia is "high income" but ~30% cheaper than France, yet shows
"high"). AI research should reconcile/replace these coarse buckets per country.

**Done looks like:** a dedicated cost section that itemises components (housing, food,
transport, healthcare, schooling/tuition, taxes…) with real estimates, shown and
**editable by the user** (adjust assumptions, household size), feeding the affordability
score. Ties into the "precise cost-of-living data" item below and tuition from schools.

**Files:** new cost model/section on `Place` + per-search overrides, `shortlist._cost_value`,
drill-down UI, `docs/xcape-design-and-criteria.md`.

### Social / professional ties criterion (friends, family, employer offices)

**Idea:** a criterion for whether a destination has the user's friends/family, or offices
of their current employer (esp. international companies) — a strong real-world pull.
**Needs design** to avoid complexity: how to capture ties (manual list? employer name →
office locations via search?), privacy, and how it weights/filters. Keep as a thinking
item for now; do not build until scoped.

### Region / city-level secondary search within a country

**Now:** the search and scoring operate at the country level. `Place` already supports
`kind = region` with a `parent_id` (some curated countries have a few regions seeded),
but there is no second-stage drill-down search.

**Done looks like:** once a country is chosen, a secondary search narrows to regions /
cities within it, scored on intra-country criteria that vary a lot within a single
country — e.g. urban vs rural, local cost-of-living differences, climate variation
(Hokkaidō ≠ Okinawa!), healthcare access, and preferred activities (nature, culture,
sea/mountains, nightlife). The user can add region-specific criteria and compare
regions/cities side by side, mirroring the country comparison board.

**Approach:**
- Extend the data model so regions/cities carry their own `attributes` (these can differ
  sharply from the country's) and facts; AI-research + cache them on demand
  (`services/place_research`, `country_facts`) keyed by region.
- Add intra-country criteria (urban/rural, activities, local cost) to the scoring
  vocabulary, possibly only surfaced in the region stage.
- A region comparison view reusing the comparison board, candidates = regions of the
  chosen country; a new `Search` scope or a sub-search linked to the parent country.
- Capture region-stage preferences (city size, activities, coast/mountains) — extend the
  profile or a per-search preference set.

**Why:** the right *country* is only half the decision; livability varies enormously by
region/city, and users will abandon if they can't get to a concrete place.

**Files:** `models/place.py` / `candidate.py` (region candidates, sub-search),
`services/shortlist.py` (region scoring + new criteria), `services/place_research.py`
(region research), `api/v1/search.py` & `candidates.py` (region endpoints),
frontend comparison/drill-down + onboarding for region-stage criteria, i18n,
`docs/xcape-design-and-criteria.md`.

### Precise cost-of-living data (replace the coarse guess)

**Now:** the cost-of-living score derives a rough monthly estimate from the symbolic
level (low/medium/high) × household size (`_COST_BAND` / `_HOUSEHOLD_FACTOR` in
`backend/app/services/shortlist.py`). It ranks sensibly against a budget but isn't a real
per-country figure.

**Done looks like:** each country carries a real estimated monthly cost of living
(per household profile, ideally in EUR), sourced rather than guessed, and the
affordability score uses that figure instead of the band proxy. Cached on the `Place`
and refreshable, like other AI/data-backed attributes.

**Approach options:**
- Add a `cost_monthly_eur` (or a cost index) to `Place`, AI-filled with web search +
  sources and cached (mirror `services/place_research` / `country_facts`); fill on demand
  and/or backfill the curated set.
- Or integrate a real dataset/API (e.g. Numbeo cost-of-living index — paid; or a public
  price-level index such as Eurostat/World Bank PPP price levels for a coarse-but-real
  signal). Numbeo gives the most relocation-relevant numbers.
- Keep the band proxy as the fallback when no real figure exists yet.

**Why:** budget is a top user concern; a real figure makes the ranking and the
affordability colour-coding trustworthy.

**Files:** `backend/app/services/shortlist.py` (`_cost_value`), `models/place.py`
(new column), a migration, `services/place_research.py` or a new cost service,
`docs/xcape-design-and-criteria.md`.
