<!-- Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

# xCape — backlog

Deferred work. Each item notes what "done" looks like, why it matters, and the files
affected. Ship items independently.

## Open

### Tool-calling in the AI chatbot

**Done looks like:** the chat assistant can take actions in the app via OpenAI
tool/function calling — e.g. refine the search, change criteria weights/filters, add or
remove a candidate country, select/unselect for comparison, drill down, and answer "why"
about a score. The model decides when to call a tool; the backend executes it (reusing
the existing services) and the UI reflects the change.

**Approach:** define tools mapping to existing endpoints/services (update_profile/filters,
add_candidate, set_selected, build/rescore, discriminate, get explanation). Thread tool
definitions into `ai_client.converse(_stream)`; handle tool-call events, execute
server-side, feed results back, and surface UI updates (re-read candidates).

**Files:** `services/ai_client.py`, `services/chat.py`, `api/v1/chat.py`, frontend chat +
state refresh.

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
