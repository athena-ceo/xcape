<!-- Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

# Visa / right-to-settle — deep-dive plan

Visa is the **gate**: without a viable pathway you cannot move, regardless of every other
criterion. It depends on TWO things the current model mostly ignores:
1. **Citizenship / origin** (free movement, visa waivers, ancestry), and
2. **Applicant category** (work, retirement, investment, ancestry/family, study, long
   residency → permanent residence → citizenship).

## Where we are today
`shortlist._visa_value` is a single computed 0-1 number: EU free-movement zone (`_EU_FOM`) →
1.0 for EU citizens else 0.3; otherwise a coarse `attrs["visa"]` easy/medium/hard scale; the
whole household judged by its **most restrictive** citizenship. The drill-down text (v4 detail
prompt) describes pathways *generically* (shared cache, origin-neutral). So: no applicant
categories, no thresholds/timelines, no per-citizenship rules beyond EU FOM.

## Target model — pathway = (destination × category), eligible per (citizenship, profile)
A pathway only exists relative to **(destination, category)**; whether THIS user can use it
depends on citizenship + situation. Split accordingly:

- **(A) Country pathway catalog — shared, cross-user.** Per `(destination, category)`: does the
  program exist, how hard, key requirements (income/investment threshold, residency→PR→
  citizenship timeline), summary + sources. Largely citizenship-independent (program rules), so
  it caches like the objective evals. **Reuse `place_custom_evals`** with `key = "visa_<category>"`
  and the structured fields in `meta` (`difficulty`, `income_eur`, `pr_years`, `citizenship_years`,
  `requirements`) — it already has versioning (`prompt_fp`), export/seed round-trip, and an
  origin-neutral prompt path. No new table.
- **(B) Citizenship + profile overlay — deterministic, per-user, no cache.** Free-movement zones
  (extend `_EU_FOM` into a small data file: EU/EEA/CH, and optionally Mercosur, CARICOM, GCC,
  trans-Tasman), visa-waiver where it matters, ancestry eligibility (**user-declared**, not
  inferred), and which categories are even *relevant* (persona → category set; budget/age →
  threshold checks).

## Categories (taxonomy)
**Confirmed set to support:** `free_movement`, `work` (skilled/employer), `retirement`
(passive-income), `investment` (golden / real-estate / business), `entrepreneur/startup`,
`digital_nomad`, `ancestry/descent`, `family` (spouse/child reunification), `student`. Plus
`long_residency` (the PR→citizenship clock) tracked as timeline metadata on each pathway rather
than a standalone category.

## Per-user synthesis (the scoring + gate)
For a user, pick the **best available pathway**:
1. Relevant categories = persona's set ∪ universally-applicable (work, family) ∪ user-declared
   (ancestry). 2. For each, check eligibility via the overlay (citizenship, income vs threshold,
   ancestry flag). 3. Difficulty = min over eligible pathways (free movement beats a golden visa
   beats nothing). 4. **Visa score = that best difficulty**; **hard gate = exclude destinations
   with no viable pathway** (this is the make-or-break filter). The current `_visa_value` becomes
   this synthesis (EU FOM stays the trivial case).

## UI
- Board visa cell: best-pathway difficulty (as now, but category-aware).
- Drill-down **"Visa pathways" panel**: the categories that apply to the user, the best one
  highlighted, each with difficulty + key requirements (income/investment, residency→citizenship
  years) + sources; a note for categories they could unlock (e.g. "investment visa if budget ≥ X").
- Onboarding/profile: a light **ancestry** question ("Might you qualify for residence/citizenship
  by ancestry anywhere? which countries?") and reuse budget as the income signal.

## Phasing
> **Status (2026-06-22):** Phase 1 ✅ (ancestry overlay in `_visa_value`), Phase 2 ✅
> (`visa_pathways` on-demand catalog in `place_custom_evals`, `visa_<category>` + meta), and the
> Phase 3 **drill-down pathways panel** ✅ (persona/ancestry-relevant categories, best-route
> highlight, thresholds + timeline + requirements + sources, progressive on-demand fill). Still
> open: folding the catalog's best-pathway into the board **visa score + hard gate** (synthesis),
> a free-movement-zone data file beyond EU, and Phase 4 household tie-in.

- **Phase 1 — foundation (no catalog):** category taxonomy; extend the citizenship overlay
  (free-movement data file; ancestry as a declared profile flag; budget→income); make visa a
  proper hard gate (exclude no-pathway). Improves today's computed visa immediately.
- **Phase 2 — catalog:** AI/curated `(destination, category)` catalog in `place_custom_evals`
  (`visa_<category>` + meta thresholds/timelines), origin-neutral, versioned. On-demand per
  (destination, category) to bound cost — NOT a bulk 217×categories run unless we choose to.
- **Phase 3 — synthesis + UI:** best-pathway selection per user; the drill-down pathways panel;
  residency→citizenship timeline surfaced.
- **Phase 4 — household tie-in:** each member's best pathway; a destination is viable only if
  ALL members have one (principal + family reunification). Couples with `docs/xcape-household-members.md`.

## Decisions (confirmed 2026-06-16)
1. **Catalog scope:** **on-demand** per (destination, category) — evaluate a pathway only when a
   user needs it (cached + shared once computed). No bulk run.
2. **Category set:** free_movement, work, retirement, investment, entrepreneur, digital_nomad,
   ancestry, family, student (long-residency as timeline metadata on each pathway).
3. **Ancestry:** user-declared profile flag (can't infer heritage) — add to onboarding/profile.
4. **Visa-waiver matrix:** skip the full bilateral matrix; lean on the on-demand catalog +
   a free-movement-zone data file.
5. **Timing:** build AFTER the objective-eval regeneration finishes and is committed (the plan is
   captured; this is the next focused project).

## Notes
- This is independent of the objective-eval regeneration (visa is computed + its own
  category-keyed cache), so it can be built without disturbing that run.
- Reusing `place_custom_evals` for the catalog means the existing versioning, export/seed and
  `reseed-data` flow all apply for free.
