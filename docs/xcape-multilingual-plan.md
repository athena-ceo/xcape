<!-- Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

# xCape — True Multi-Lingual Conversion (Backlog Plan)

**Status:** Backlog candidate (not scheduled). Drafted 2026-06-26.

**Goal:** Convert xCape from a hard-wired French/English app to one that supports an
**arbitrary number of languages**, while **minimizing large/expensive AI calls**.

---

## Why this is needed

The FR/EN assumption is baked into three layers:

- **Storage** — paired columns / JSON keys everywhere:
  - `Place.summary_fr` / `summary_en` (`backend/app/models/place.py:28-29`)
  - `Place.criteria_detail[key].summary_fr/_en` (JSON, `place.py:34`)
  - `PlaceCustomEval.summary_fr` / `summary_en` (`backend/app/models/custom_eval.py:33-34`)
  - `PlaceCustomEval.meta`: `requirements_fr/_en`, `metric_fr/_en`
  - Affordability notes `{component}_note_fr/_en` (`backend/app/services/affordability.py`)
  - Frontend registry/persona data: `label_fr/_en`, `blurb_fr/_en`,
    `value_labels.{fr,en}` (`src/services/criteria.ts`)
  - Hardcoded label dicts: `_REASON_LABELS` (`shortlist.py:54-69`),
    `CATEGORY_LABELS` (`visa_pathways.py:44-54`), report `_T` (`report.py:28-46`)
- **AI generation** — 6 generators each ask the model for **both languages in one call**:
  `research_place`, `criterion_detail_one` (`place_research.py`), `criterion_eval.evaluate`
  (`criterion_eval.py`), `visa_pathways.evaluate_pathway`, `affordability.evaluate_breakdown`,
  `custom_criteria.localize_label`. The expensive part (web search + scoring) is
  language-neutral but currently fused with prose generation.
- **UI** — `Language = 'fr' | 'en'` (`src/i18n/index.tsx:11`), ~17 `lang === 'fr' ? x : y`
  ternaries, a two-`<option>` switcher (`src/components/Header.tsx:61-69`), two hand-written
  dictionaries (`fr.ts` / `en.ts`), admin forms with hardcoded EN/FR inputs, and
  `LOCALE_LANGUAGE = { fr, en }` (`src/data/profileOptions.ts:30`).

**Foundation already in place:** scores / structured data are computed **once and shared**
(not per-language), and there is **no per-language cache duplication**. Country names already
localize via `Intl.DisplayNames` (`src/i18n/places.ts`), so they need no migration.

---

## Core idea (two changes, applied consistently)

1. **Replace every `*_fr`/`*_en` pair with a language-keyed map** `{ "fr": …, "en": …, "es": … }`,
   read through a single resolver `pick(map, lang)` → requested → `base_language` → any non-empty.
   One abstraction removes all the special-casing.

2. **Split AI work into "evaluate once, localize lazily."** Web search + scoring + structured
   facts are language-neutral and cached **once per (place, criterion)** — never multiplied by
   language. Localized prose lives in the map and is filled **on demand, one language at a time,
   via a cheap no-search `translate()` call** when a user actually views that cell in that
   language. Cached and shared across all users of that language.

This is the cost win: **adding the Nth language triggers zero re-evaluation and zero web
search.** Per-language cost is bounded by *actual views* of short (1–2 sentence) strings —
consistent with the existing "self-heal lazily on view" principle.

### Decisions (confirmed 2026-06-26)

- **AI strategy:** Evaluate once + lazy translate (not per-language native generation, not
  generate-all-up-front). The first-viewed language gets native prose; others are translated.
- **Translation UX:** A subtle "auto-translated" marker on machine-translated prose.
- **First validation language:** **Spanish** (`es`).

---

## AI cost model

| Event | Today (FR+EN) | After migration |
|---|---|---|
| First view of a cell (any language) | 1 call: search + score + FR + EN prose | 1 call: search + score + prose in **that one language** |
| Same cell, second language | already in row (free) | 1 **cheap** call: translate cached prose (no search), cached |
| Platform adds a new language | — | **nothing** until viewed; then per-cell cheap translate on view |
| Re-evaluation (prompt version bump) | re-runs search for both langs | re-runs search **once** (language-neutral); prose re-localized lazily |

The costly path (web search/reasoning) stays at **once per cell, ever**, regardless of language
count. French (primary market, generated directly on first view) keeps native quality with no
translation hop.

---

## Target data shape

- Localized text → `Record<langcode, string>`, e.g. `summary: {"fr":…,"en":…,"es":…}`.
- Provenance for the marker: a parallel `summary_src: {lang: "native" | "auto"}` (or a small
  per-entry flag).
- Resolver: `pick(map, lang)` (requested → `base_language` → any non-empty).

---

## Implementation phases (each independently shippable)

### Phase A — Plumbing (small, low-risk, no behavior change). Ships still FR/EN.
- Backend `config.py`: `supported_languages: list[str] = ["fr","en"]`, `base_language = "en"`.
  Remove `lang in ("fr","en")` clamps (`board.py`, `report.py`); validate against the config list.
- Backend `i18n` helpers: `pick()`, `set_lang()`, plus transitional readers that also understand
  legacy `_fr/_en`.
- Frontend: replace the 17 `lang === 'fr' ? …` ternaries with `localize(map, lang)`;
  `Language = 'fr' | 'en'` → `string`; dynamic switcher + `LOCALE_LANGUAGE` from config;
  admin EN/FR inputs → per-language loop/tabs. Loader structured so a new dict file is the only
  addition needed to add a UI language.

### Phase B — Storage migration to maps (medium/large, needs care).
- Alembic migration: `*_fr/_en` columns + JSON pairs → single JSON map columns/keys, backfilling
  existing rows to `{"fr":…,"en":…}` with `src = native`. Idempotent + constraint/data test
  (per the backend checklist). Covers `Place`, `PlaceCustomEval`, `criteria_detail[key]`,
  `meta.requirements/metric`, affordability notes, and frontend-facing registry/persona data.
- Update schemas + service read sites (`board.py`, `report.py`,
  `criterion_eval.reason_from_eval`, etc.) to emit maps. No external API consumers → update FE in
  lockstep (no back-compat shim needed).

### Phase C — AI decoupling (large, the cost win).
- Change the 6 generators' schemas/prompts to return **one** `summary` in the requested language
  plus the existing language-neutral fields (score, sources, metric values, components,
  thresholds). Write prose into the map flagged `native`.
- Add `translate(text, target_lang)` service: cheapest model, no web search, batched per cell,
  records provenance `auto`.
- Lazy fill: in the `/…/generate` self-heal endpoints, when `pick(map, lang)` is empty, translate
  from base/any existing entry, cache, flag `auto`. No bulk backfill.
- `custom_criteria.localize_label` and `value_labels` follow the same map + lazy-translate pattern.

### Phase D — Spanish on.
- Add `es` to `supported_languages`; ship `es.ts` (one-time AI-assisted offline translation of
  `fr.ts`/`en.ts` — not a runtime cost). Validates the whole path with real content.
- Subtle "auto-translated" marker wherever `src === "auto"`.

**Suggested start:** Phase A — mechanical, low-risk, and unblocks everything else; delivers the
generalization even before any new language is added.

---

## Risks to watch

- **Table layout** — Spanish/German prose is longer; the comparison board's `table-fixed`
  wrapping (added 2026-06-26) already mitigates column-width blowups, but re-check on real ES content.
- **Migration correctness** — the JSON map backfill must preserve every existing FR/EN string;
  cover with a constraint/data test.
- **Translation quality on factual prose** — acceptable for 1–2 sentence summaries; the marker
  sets expectations, and native generation still happens for the first-viewed language.
- **Locale validation** — once `lang` is free-form, reject/repair unknown codes against the
  config list rather than silently clamping to `fr`.

---

## Key file references

- AI client: `backend/app/services/ai_client.py`
- Generators: `backend/app/services/{place_research,criterion_eval,visa_pathways,affordability,custom_criteria}.py`
- Read sites / assembly: `backend/app/services/{board,report,shortlist}.py`
- Lazy-generation endpoints: `backend/app/api/v1/places.py`
- Models: `backend/app/models/{place,custom_eval,user}.py`
- Frontend i18n: `src/i18n/{index.tsx,fr.ts,en.ts,places.ts}`, `src/components/Header.tsx`
- Frontend data selection: `src/services/criteria.ts`, `src/data/profileOptions.ts`,
  and the ~17 ternary sites (Drilldown, VisaFinder, Onboarding, ProfilePage, ComparisonPlayground,
  CommunitySelect, AdminCriteria, AdminPersonas).
