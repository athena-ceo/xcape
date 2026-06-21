<!-- Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

# Exploration & discovery — design (TODO)

Two related wants, both about looking **beyond the curated top-5 board**:
1. a built-in way to **view all country results** (full ranked list), and
2. a way to **pull in random / wildcard countries** to provoke ideas and discussion.

Both are feature-creep risks, so the governing rule is **progressive disclosure**: the default
board stays minimal (the confident answer); exploration lives on a separate surface reached by a
single quiet affordance. Casual users never see it; serious users discover it.

## 1. "All countries" view
- Today: the board shows top-5 selected + a small suggestion pool. There's no way to see the
  full ranking of all ~217 countries against the user's current weights/filters.
- Proposal: a separate **Explore** route (e.g. `/explore/:searchId`) showing the **full ranked
  list** — compact rows (flag · name · overall score · 2-3 top criteria), sortable and
  text-filterable, each row → add-to-board / open drill-down. Reuses the existing scoring +
  filter logic (no new evals).
- **Filters:** default to showing only filter-passing countries (consistent with the board),
  with a "show excluded too" toggle that lists violators with the ⚠ flag + reason — so the user
  can audit *why* something dropped.
- **Mobile bonus:** the side-by-side matrix is poor on small screens; this ranked **list** is
  naturally mobile-friendly, so it doubles as the primary mobile results view (not pure
  addition — it also fixes a real mobile gap).

## 2. Wildcards (serendipity)
- Purpose: break the filter bubble, spark "have you considered…?" conversations.
- Selection options (best → simplest):
  - **Dark horses** — strong on a criterion the user weights but just outside the shortlist, or
    surprisingly high somewhere unexpected.
  - **Diverse** — random across regions not represented in the current board.
  - **Pure random** — provocative but can be absurd; use sparingly.
- Presentation: a small, clearly-labelled "**Sparks / wildcards — not your top matches, just to
  provoke ideas**" strip in the Explore view (never on the main board, to avoid muddying the
  answer). One tap → open the drill-down or **ask the assistant** "why might {country} surprise
  me?" (feeds the existing chat with that place's context).
- Must be visually and verbally distinct from recommendations so they never read as endorsements.

## Feature-creep guardrails
- Nothing here is added to the default board. A single "**Explore all countries**" link sits
  quietly below the board (and a matching entry in the nav/▸ overflow on mobile).
- Wildcards are opt-in within Explore, labelled as non-recommendations.
- Keep the Explore view read-mostly: rank, scan, add-to-board, drill-down, ask — no settings
  clutter (criteria tuning stays on the board).

## Phasing
- **Phase 1:** Explore route = full ranked list (reuses scoring), add-to-board + drill-down,
  filter-passing by default with "show excluded". Doubles as mobile results.
- **Phase 2:** Wildcards strip (dark-horse / diverse selection) with "ask the assistant why".
- **Phase 3:** smarter wildcard selection (surprising-on-a-weighted-criterion, region
  diversity), and a compact "compare any country to my board" quick-add.

## Open questions
- Is Explore a new route or a tab within the comparison page? A route keeps the board clean and
  is easy to deep-link/share; a tab keeps context. Lean route, with a back-to-board control.
- How many wildcards at once (3?), and do they persist or reshuffle each visit? Lean: 3,
  reshuffle on demand via a "shuffle" control.
