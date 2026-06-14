<!-- Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

# xCape — Design language & criteria

Companion to the requirements and architecture docs. Defines the visual language, the
relocation criteria, and how scoring / filtering work.

## Design language

**Palette — turquoise blue, welcoming.** Brand scale (`tailwind.config.js`):

| Token | Hex | Use |
|-------|-----|-----|
| turquoise-50 | `#e1f5ee` | tints, chips, surfaces |
| turquoise-100 | `#9fe1cb` | borders |
| turquoise-400 | `#1d9e75` | accents, progress |
| turquoise-600 | `#0f6e56` | primary buttons, links, brand |
| turquoise-900 | `#04342c` | headings, body |

Page background `#f4fbf9`. Cards: white, `border-turquoise-100`, rounded.

**Quality colour coding** (comparison cells) — light tints that complement turquoise:

| Tier | Meaning | Classes |
|------|---------|---------|
| good | green — strong for this user | `bg-emerald-50 text-emerald-800` |
| ok | amber — weak / acceptable | `bg-amber-50 text-amber-900` |
| bad | red — a no-go | `bg-red-50 text-red-800` |

A legend sits above the comparison table. The current-country (baseline) column is a
neutral turquoise tint — it's the reference, not graded.

**Typography & components.** Inter / system sans. Headings in turquoise-900, weight 500.
Shared components: `Chip` (selectable pill), `Spinner` (AI activity), `VoiceButton` /
`VoiceField` (mic + text), `CountryMultiSelect`, `LanguageMultiSelect`, `Markdown`
(sanitized chat answers). Bilingual FR/EN; French default; no hard-coded user strings.

## Criteria

Each `Place` carries coarse comparative buckets in `attributes`. Higher = better for the
user unless noted.

| Criterion | Buckets | Notes |
|-----------|---------|-------|
| cost_of_living | low / medium / high | **low is best** (cheaper) |
| climate | cold / temperate / mild / warm / tropical | scored against the user's preference |
| language_ease | (static) french / english / easy / medium / hard | display shows the country's actual `languages`; scored against the user's **known languages** |
| healthcare | strong / good / basic | |
| safety | high / medium / low | |
| political_stability | high / medium / low | |
| inclusion | (derived) | tolerance / acceptance, scored against the **communities the user cares about** (see below) |
| gender_equality | high / medium / low | legal rights, equal pay, fair treatment |
| tax | low / medium / high | **low is best** (lighter burden) |
| visa | easy / medium / hard | scored from **citizenship**, not residence (see below) |
| expat_community | large / medium / small | |
| culture | high / medium / low | cultural activities, arts, events |
| food | high / medium / low | food culture / cuisine |
| nature | high / medium / low | |
| internet | fast / ok / slow | |

Plus `languages` (list a resident actually uses), `social_acceptance` (per-community
acceptance: lgbtq / jewish / muslim / ethnic_minorities / immigrants, each high/mixed/low)
and `openness` (general societal openness) feeding the inclusion criterion, and — for the
drill-down — cached `facts` (capital, population, region, flag, coords, photo) and
`criteria_detail` (sourced AI explanations).

**User-defined criteria** can be added per search (a phrase like "vegan-friendly"); the AI
rates each country good/ok/bad with a justification, cached in `place_custom_evals` and
scored alongside the built-ins.

## Scoring

Score = weighted average of each criterion's quality (0–1), ×100. Contributions sum to
the score (see the click-through explainer on any score).

**Weights** (`services/shortlist._effective_weights`):
1. Baseline defaults (cost, healthcare, safety, political stability ≈ 1.0; language,
   climate ≈ 0.8; visa 0.7; tax 0.5).
2. **Reason-for-leaving boosts** — leaving for politics boosts political_stability, for
   cost boosts cost_of_living, etc.
3. **Household** — families get a healthcare/safety bump.
4. **User priorities / criteria settings** — explicit weights override the above.

**Special criteria:**
- **Cost of living** — when the user sets a **monthly budget**, the symbolic level is
  turned into a coarse monthly-cost estimate (level × household size) and scored by how
  comfortably the budget covers it (affordability), rather than just "cheaper is better".
  Without a budget it falls back to the plain scale. The per-country drill-down gives
  real figures with sources.
- **Language** — full marks if the user speaks a language used in the country; otherwise
  falls back to learn-difficulty, softened if willing to learn.
- **Visa / mobility** — driven by the household's **citizenship(s)**: citizen of the
  destination or an EU/EEA/CH citizen moving within that zone → free movement; a non-EU
  citizen (even if resident in the EU) → hard for EU destinations.
- **Climate** — full marks when it matches the user's preference.
- **Inclusion** — the user optionally flags communities whose acceptance matters to them
  (`profile.minority_groups`, private). The score is the **worst-accepted** of those
  communities in `social_acceptance` (a place hostile to even one shouldn't look safe);
  missing data for a community is neutral. With no communities flagged it falls back to the
  country's general `openness`. Selecting communities (or the "discrimination"
  reason-for-leaving) up-weights inclusion.

**Quality tiers** for colour coding: ≥0.70 good · ≥0.45 ok · else bad.

## Filters (hard constraints)

Beyond weights, criteria can be **filters** that remove countries from the pool
(`services/shortlist.passes_filters`), set via the comparison board's "Criteria
settings":
- **language** — only countries where the user can communicate (known ∩ country
  languages).
- **climate** — only a chosen climate.
- **visa** — only places with easy mobility (citizen / EU-FOM / easy visa).
- **inclusion** — "only welcoming places" excludes countries where the user's flagged
  communities aren't accepted.
- ordinal criteria support a minimum-acceptable bucket.

Applying settings rebuilds the shortlist from the full pool, so filters change which
countries qualify (e.g. an Arabic speaker who requires a communicable language sees
Arabic-speaking countries). If filters exclude everything, the unfiltered pool is shown.

## Data sources

- **Seed**: every country (~217) — World Bank (roster, capital, region, coords, income)
  + Wikidata (official languages). 27 curated countries keep hand-tuned attributes.
- **On demand (AI, cached)**: country research (full attributes), per-criterion detail
  with sources, media, and on-demand criterion fill — all written back to the `Place`.
- **Drill-down facts**: World Bank + flagcdn (flag) + Wikipedia (capital photo).

## Admin

`is_admin` users get an **Admin** link in the header → `/admin`. Grant it with
`./xcape.sh make-admin <dev|prod> <email>` (re-login to see the link). The admin area
covers users, searches, the place database, and the AI usage log.
