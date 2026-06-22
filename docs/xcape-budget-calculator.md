<!-- Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

# TODO — monthly budget / affordability calculator (drill-down)

## Problem
We collect `profile.budget_monthly` (the retiree persona even asks for monthly income), but it
is only used coarsely — to colour the **cost of living** band (`comparison._COST_BAND`). It is
**not** used to answer the question a relocator actually has: *"can I afford to live in country X
on my budget, and does my income clear that country's visa income threshold?"*

## Proposed
A small **budget / affordability calculator on the country drill-down page**:
- Inputs: the user's `budget_monthly` (prefilled, editable) and household size.
- Country data: typical monthly costs (rent, utilities, food, healthcare, transport) — from the
  cost-of-living eval / a costs dataset — scaled to the household.
- Output: estimated monthly cost vs budget (surplus/deficit), an affordability verdict, and a
  breakdown. Optionally a city selector (capital vs cheaper city).
- **Tie-in to visa:** compare annualised income (`budget_monthly × 12`) against the visa
  pathways' `income_eur` thresholds (already captured in `visa_pathways` meta) to flag which
  income-based routes (retirement / passive-income, digital nomad) the user's income qualifies
  for. This is the eligibility piece deliberately left out of the visa "best route" synthesis.

## Notes
- Reuses: `profile.budget_monthly`, the cost-of-living eval, and `visa_pathways` `income_eur`.
- Surfaced from the drill-down (per country), where the user is already weighing one place.
- Scope/size: medium. Needs a per-country cost breakdown source (currently we only have a coarse
  cost band) — either an AI-generated cost breakdown (cache like the other evals) or a dataset.
