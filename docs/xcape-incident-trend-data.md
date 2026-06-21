<!-- Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

# Anti-community incident trends — data design

Worried-community users (antisemitism, Islamophobia, homophobia; also political-takeover
fears) care about the **derivative** — is hostility rising or falling — at least as much as the
absolute level. This note records what's built (A) and the more rigorous option (B).

## A — Structured AI capture (IMPLEMENTED, 2026-06-16)

Trend-sensitive criteria use a dedicated **"trend" lens** in `criterion_eval`
(`TREND_LENS_KEYS = {safety, political_stability}` + the per-community `Safety for my
community` criterion). Their eval returns a richer schema and we store the structured part in
`place_custom_evals.meta`:

```json
{ "level": "high|moderate|low", "trend": "improving|stable|worsening",
  "window": "2023–2025", "metric": "one-line factual basis, citing a recognised monitor" }
```

- The 0–100 score must reflect BOTH level and trajectory (high-but-worsening < stable-high).
- The prompt names canonical monitors (ADL/CST for Jewish communities, ILGA for LGBTQ+,
  OSCE-ODIHR / EU-FRA hate-crime data, national stats) and asks for a source from one.
- Surfaced in the drill-down as a level + trend arrow (↗/→/↘) + window + the metric line.
- Versioned via `prompt_fp` (lens is part of the fingerprint), round-trips through
  `export-evals` / seed.

**Limits:** still AI-mediated and web-search-grounded — the figures are model-reported, not
verified against a dataset; coverage/quality varies by country and community; "cite a monitor"
is a nudge, not a guarantee.

## B — Grounded data pipeline (PROPOSED, not built)

Make the numbers real: ingest published datasets into a small fact table and have the AI
*explain* them rather than source them.

- **Sources:** OSCE-ODIHR hate-crime reporting (per country, per bias-motivation, annual);
  EU-FRA fundamental-rights surveys; ADL / CST / SPCJ annual antisemitism figures; ILGA-Europe
  Rainbow Map (legal index, annual); national police/interior statistics where available.
- **Model:** `incident_stat(place_id, community, year, count|index, source, url)` — a thin
  table keyed by (country, community, year). Compute level + derivative (YoY / 3-yr slope)
  deterministically from it.
- **Flow:** periodic ingest job (per source/format) → normalise to the fact table → the trend
  lens reads real figures and the AI writes the prose around them (no invented numbers).
- **Caveats:** datasets lag (often 12–24 months) and undercount (reporting bias); coverage is
  uneven (strong for EU/OECD, thin elsewhere); definitions differ across sources — normalise
  carefully and show the source + year next to any figure. Per-community coverage is best for
  antisemitism and LGBTQ+, weaker for others.
- **Effort:** medium-large (one adapter per source + scheduling + reconciliation). Worth it if
  community safety becomes a flagship / monetised use case, since credibility is the product.

Start point if pursued: one source end-to-end (OSCE-ODIHR, broad country coverage) feeding the
existing trend lens, then add ADL/CST/ILGA. A's `meta` shape is already the display contract,
so B can populate it without UI changes.
