<!-- Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

# Per-household-member analysis — design (TODO)

Today a household is modelled as **one merged person**: citizenships are unioned, there is one
set of priorities/weights, one persona, one community list. That's simple and right for the
common case, but it hides the most interesting relocation conversations — when members of a
family want or need different things. Goal: **keep the one-voice default**, add an **optional**
per-member layer, and surface **side-by-side** comparisons where members diverge.

## Where member differences actually matter (worth modelling)
1. **Visa / right to settle** — the big one. Each member has their own citizenship → their own
   pathway. A non-EU spouse can flip a country from trivial to impossible. The household can
   only move where *every* member has a viable path (principal + dependents via family
   reunification). Ties directly into the visa deep-dive (`docs` / TODO).
2. **Community safety** — "safety for my community" is inherently per-member (one member is
   Jewish, another LGBTQ+, another neither). Today it's merged onto the household.
3. **Language** — known languages differ per person → `language_ease` is per-member.
4. **Priorities / persona** — a working spouse (career), a retiree parent (healthcare/visa), a
   teenager (education/culture) pull in different directions. Different weight profiles.
5. **Role / age** — education matters for children; retiree healthcare for an elder; work visa
   for working-age adults.

## Principle: progressive disclosure
- **Default (unchanged):** the household is one merged profile → one board. Most users never
  see the member layer.
- **Opt-in:** after the board exists, "This is a household decision — add the people involved."
  Each member is a *light* form: name/label, citizenship(s), role (adult / child / retiree),
  optional top priorities, optional communities, known languages. Reuse the persona picker per
  member. Anything left blank inherits the household default.
- The **household board stays primary**; per-member is a secondary lens (a view toggle / panel),
  never forced.

## Data model
Add an optional `HouseholdMember` (FK → profile): `label`, `role`, `citizenships[]`,
`languages{}`, `minority_groups[]`, `persona`, `criteria_weights{}`. The existing profile fields
remain the **household aggregate / principal** and the fallback for any unset member field. No
members ⇒ today's behaviour exactly (backward compatible, no migration impact on existing rows).

## Scoring & reconciliation (the core)
Compute a **per-member score** per country (each member's weights + citizenship + communities),
then reconcile into the household view:
- **Hard constraints = union / veto.** A country must clear *every* member's hard filters, and
  *every* member must have a viable visa pathway. Any member's dealbreaker excludes it. (This is
  why the visa work and this work reinforce each other.)
- **Soft score = blend.** Household score = mean (optionally weighted, e.g. adults > children)
  of per-member soft scores. Keeps a single ranking for the simple view.
- **Divergence = feature, not noise.** Track per-country variance across members to power the
  "interesting discussions" view (below).

## Side-by-side & "where you differ"
- **By-member view** on the board: a toggle "Household | By member"; By-member shows each
  member's overall score per shortlisted country (small matrix: members × countries), with each
  member's top win/loss.
- **Divergence finder:** "Compromise" countries (high *minimum* across members — everyone's OK)
  vs "polarising" ones (high variance — great for one, weak for another), so the family can see
  the trade-offs explicitly. e.g. "Portugal: great for you and the kids, hard visa for your
  (non-EU) spouse."
- **Per-criterion conflict highlights:** flag the few criteria where members most disagree
  (one weights it 3, another 0), since those are the real negotiation points.

## Phasing
- **Phase 1 (MVP):** optional members with citizenship + priorities + communities; keep the
  household board's ranking; add a By-member score panel + a "biggest disagreements" highlight;
  hard filters = union; visa must work for all (using the current coarse per-citizenship visa).
- **Phase 2:** per-member personas/criteria; conflict highlights; weighted blend (adults vs
  children).
- **Phase 3:** family-reunification-aware visa pathways (depends on the visa deep-dive);
  compromise optimiser ("best country where everyone scores ≥ X").

## Open questions
- Should the household ranking be the blended mean, or "best country where the *worst-off*
  member is happiest" (maximin)? Probably offer both as a sort.
- How much per-member onboarding before it stops feeling simple? Likely: citizenship + role are
  the only near-required extras (they drive visa); everything else inherits the household default.
- Privacy: members' communities are sensitive; keep them scoring-only, never displayed as
  identifying labels (as today for the single profile).
