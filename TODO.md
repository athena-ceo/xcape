<!-- Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

# xCape — backlog

Deferred work. Each item notes what "done" looks like, why it matters, and the files
affected. Ship items independently.

## Open

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
