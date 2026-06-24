# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Monthly budget / affordability calculator for the country drill-down.

Answers the question a relocator actually has: *"can I afford to live in country X on my
budget, and does my income clear that country's visa income threshold?"* — beyond the coarse
cost-of-living band used for ranking (see ``shortlist._cost_value``).

Two halves:

- **Cost breakdown (AI, cached).** A per-country monthly cost breakdown for a single person in
  euros (rent, utilities, food, healthcare, transport, other), cached in ``place_custom_evals``
  under ``key = "cost_breakdown"`` exactly like the objective evals and the visa catalog —
  versioned via ``prompt_fp``, shared cross-user, evaluated on-demand. No new table.
- **Calculator (deterministic, per-request).** Scales that single-person breakdown to the
  household size, totals it, and compares it to the user's editable monthly budget → surplus /
  deficit + verdict. Plus the **visa tie-in**: annualised income (budget × 12) vs the cached
  visa pathways' ``income_eur`` thresholds, flagging the income-based routes (retirement,
  digital nomad) the income qualifies for.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.custom_eval import PlaceCustomEval
from app.models.place import Place
from app.models.profile import Profile
from app.services import ai_client, fx, visa_pathways
from app.services.criterion_eval import _fresh, level_from_score

# Bump when the breakdown prompt/schema below changes in a way that should invalidate cached rows.
COST_PROMPT_VERSION = "3"  # v3: tenure-aware housing (rent vs buy) cached alongside each other
BREAKDOWN_KEY = "cost_breakdown"

# Every figure the AI returns and we cache (shared, EUR). The two housing figures — `rent` and
# `buy` (a typical monthly mortgage payment) — are BOTH cached so the per-user tenure just selects
# which one to show; the cache stays user-neutral. The figures are scaled to the household by the
# per-component marginal factor below.
COMPONENTS = ("rent", "buy", "utilities", "food", "healthcare", "transport", "other")

# How each NON-housing component grows with each additional household member
# (factor = 1 + marginal × (N-1)). Utilities are largely shared (one home); food scales nearly
# per-head, healthcare is per-person; transport and the rest sit in between. N=1 → every factor
# is 1.0. Housing (rent/buy) is handled separately by `housing_factor`, which scales by the
# number of BEDROOMS the household needs rather than a flat per-head marginal.
_HH_MARGINAL = {
    "utilities": 0.25, "food": 0.85,
    "healthcare": 1.0, "transport": 0.6, "other": 0.55,
}

# Marginal cost of each ADDITIONAL bedroom beyond the first, as a fraction of a one-bedroom home.
# The first bedroom carries the fixed cost (kitchen, bathroom, living space); each extra room adds
# proportionally less, so a 3-bed is ~2× a 1-bed, not 3×.
_BEDROOM_MARGINAL = 0.5


def bedrooms_for_size(size: int) -> int:
    """Bedrooms a household of ``size`` needs: one shared by the primary occupant or couple, plus
    one for each additional member (typically children). 1–2 people → 1 BR, 3 → 2 BR, 4 → 3 BR."""
    n = max(1, int(size or 1))
    return max(1, n - 1)


def housing_factor(size: int) -> float:
    """Multiplier applied to a single-person (one-bedroom) housing cost for a household of
    ``size``, driven by the bedroom count it needs rather than a flat per-head marginal."""
    return 1.0 + _BEDROOM_MARGINAL * (bedrooms_for_size(size) - 1)


def _display_components(tenure: str | None) -> tuple[str, ...]:
    """The components actually shown for a user, in order — the housing slot is the monthly
    mortgage (`buy`) when they want to buy, otherwise rent. Never both (that would double-count)."""
    housing = "buy" if tenure == "buy" else "rent"
    return (housing, "utilities", "food", "healthcare", "transport", "other")

# Default household SIZE inferred from the coarse household_type (the calculator input is editable).
_DEFAULT_SIZE = {"single": 1, "couple": 2, "family": 4}

# Income-based visa categories whose threshold the annualised budget is checked against (and which
# the generate step ensures are evaluated so the tie-in is populated). Other categories gate on
# investment/employment, not income, so they are not income-eligibility routes.
INCOME_CATEGORIES = ("retirement", "digital_nomad")

# Verdict bands on the coverage ratio (budget / estimated monthly cost).
_COMFORTABLE, _MANAGEABLE, _TIGHT = 1.25, 1.0, 0.85


def default_household_size(profile: Profile | None) -> int:
    return _DEFAULT_SIZE.get(getattr(profile, "household_type", None), 1) if profile else 1


def household_factor(component: str, size: int) -> float:
    """Multiplier applied to a single-person component cost for a household of ``size``. Housing
    (rent/buy) scales by the number of bedrooms needed; every other component by its per-head
    marginal."""
    if component in ("rent", "buy"):
        return housing_factor(size)
    n = max(1, int(size or 1))
    return 1.0 + _HH_MARGINAL.get(component, 0.6) * (n - 1)


def _fp() -> str:
    """Fingerprint for a cost-breakdown cell — the invariant part of the prompt (place excluded)."""
    raw = f"{COST_PROMPT_VERSION}\x1fcost_breakdown"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _schema() -> dict:
    """Per component: a single-person monthly figure (`{c}_eur`) and a short FR/EN justification
    (`{c}_note_fr` / `{c}_note_en`) of how it was derived, for the per-entry explanation popup."""
    num = {"type": "number", "minimum": 0}
    props: dict = {}
    required: list[str] = []
    for c in COMPONENTS:
        props[f"{c}_eur"] = num                       # typical monthly cost for ONE person, euros
        props[f"{c}_note_fr"] = {"type": "string"}    # how this figure was derived (FR)
        props[f"{c}_note_en"] = {"type": "string"}    # how this figure was derived (EN)
        required += [f"{c}_eur", f"{c}_note_fr", f"{c}_note_en"]
    props["summary_fr"] = {"type": "string"}
    props["summary_en"] = {"type": "string"}
    props["sources"] = {"type": "array", "items": {"type": "string"}}
    required += ["summary_fr", "summary_en", "sources"]
    return {
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


def evaluate_breakdown(
    db: Session, place: Place, *,
    force: bool = False, stale_days: int = 0, user_id: int | None = None,
) -> PlaceCustomEval | None:
    """Assess one country's single-person monthly cost breakdown (cache-first). Returns the row,
    or None if AI is off."""
    existing = (
        db.query(PlaceCustomEval)
        .filter(PlaceCustomEval.place_id == place.id, PlaceCustomEval.key == BREAKDOWN_KEY)
        .first()
    )
    fp = _fp()
    if existing and not force and _fresh(existing, fp, stale_days):
        return existing

    prompt = (
        f"Estimate the typical MONTHLY cost of living for ONE person settling in {place.name} as a "
        f"foreign resident, in euros (€). Assume a modest, mid-range lifestyle in a typical city "
        f"(not the most expensive neighbourhood, not the cheapest rural area), renting a small "
        f"one-bedroom home. Break the total into these components, each a monthly figure in euros:\n"
        f"- rent_eur: monthly rent for a small one-bedroom flat.\n"
        f"- buy_eur: the typical MONTHLY cost of BUYING that same small one-bedroom home instead of "
        f"renting — i.e. the monthly mortgage repayment for such a property purchased with a normal "
        f"local down payment at current local mortgage rates. (In the note, state the assumed price, "
        f"deposit and rate.)\n"
        f"- utilities_eur: electricity, water, heating, internet, mobile.\n"
        f"- food_eur: groceries and a few modest meals out.\n"
        f"- healthcare_eur: typical private health insurance / out-of-pocket for a foreign "
        f"resident not yet in the public system.\n"
        f"- transport_eur: public transport pass and occasional taxis, or modest car running costs.\n"
        f"- other_eur: everything else (clothing, leisure, household goods, incidentals).\n"
        f"Give realistic single-person figures (the caller scales them to larger households). For "
        f"EACH component also add a short one-sentence justification in French ({{c}}_note_fr) and "
        f"English ({{c}}_note_en) explaining how the figure was derived — what it assumes or "
        f"includes (e.g. the type of area, what the figure covers, a concrete reference point) — "
        f"so a reader can see why this number. Then add a concrete 1-2 sentence overall summary in "
        f"French (summary_fr) and English (summary_en). Write as a neutral, friendly advisor — do "
        f"NOT write in the first person (no \"I\", \"we\", \"my\", \"our\") and do NOT merely "
        f"restate every number. Put sources ONLY in the sources array as bare https URLs. Use web "
        f"search and favour the most recent data (2025–2026)."
    )
    try:
        data = ai_client.respond_json(
            prompt, _schema(), schema_name="cost_breakdown", web_search=True,
            model=settings.openai_chat_model, kind="custom", db=db, user_id=user_id,
        )
    except ai_client.AIUnavailable:
        return None

    comps = {c: float(data.get(f"{c}_eur") or 0) for c in COMPONENTS}
    # Per-component justification (how each single-person figure was derived), both languages, for
    # the per-entry explanation popup. Empty strings are dropped so the UI falls back gracefully.
    notes = {
        c: {"fr": data.get(f"{c}_note_fr") or "", "en": data.get(f"{c}_note_en") or ""}
        for c in COMPONENTS
    }
    # Reference total uses the rent housing slot (not rent + buy, which would double-count housing).
    total = round(sum(comps.get(c, 0.0) for c in _display_components(None)))
    meta = {"components": comps, "notes": notes, "total_single_eur": total}
    fields = dict(
        label="Monthly cost breakdown", score=None, level=level_from_score(None),
        summary_fr=data.get("summary_fr"), summary_en=data.get("summary_en"),
        sources=data.get("sources", []), meta=meta, prompt_fp=fp,
        freshness_at=datetime.now(timezone.utc),
    )
    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
        db.commit()
        db.refresh(existing)
        return existing
    ev = PlaceCustomEval(place_id=place.id, key=BREAKDOWN_KEY, **fields)
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def cached_breakdown(db: Session, place_id: int) -> PlaceCustomEval | None:
    """The cached cost-breakdown row for a place, or None (no AI)."""
    return (
        db.query(PlaceCustomEval)
        .filter(PlaceCustomEval.place_id == place_id, PlaceCustomEval.key == BREAKDOWN_KEY)
        .first()
    )


def _verdict(ratio: float) -> str:
    if ratio >= _COMFORTABLE:
        return "comfortable"
    if ratio >= _MANAGEABLE:
        return "manageable"
    if ratio >= _TIGHT:
        return "tight"
    return "insufficient"


def income_pathways(
    db: Session, place_id: int, annual_income: int | None, lang: str = "en", *, rate: float = 1.0,
) -> list[dict]:
    """Income-based visa routes (cached) the annualised budget is checked against. Each carries the
    threshold (converted from the canonical EUR to the user's currency) and whether the income
    clears it. Routes with no income threshold are skipped."""
    rows = visa_pathways.cached_rows(db, place_id)
    out: list[dict] = []
    for cat in INCOME_CATEGORIES:
        ev = rows.get(cat)
        if ev is None:
            continue
        m = ev.meta or {}
        threshold_eur = m.get("income_eur")
        if not m.get("exists", True) or threshold_eur is None:
            continue
        threshold = round(threshold_eur * rate)  # both income and threshold in the user's currency
        out.append({
            "category": cat,
            "label": visa_pathways.category_label(cat, lang),
            "income": threshold,
            "qualifies": annual_income is not None and annual_income >= threshold,
        })
    return out


def compute(
    db: Session, place: Place, profile: Profile | None, *,
    budget_monthly: int | None, household_size: int | None, currency: str = "EUR", lang: str = "en",
) -> dict:
    """Assemble the affordability payload from the cached breakdown (or `pending`), the household
    scaling, the budget comparison, and the visa income tie-in. The cached costs / thresholds are
    canonical EUR; every money figure is converted to `currency` (the user's budgeting currency, in
    which `budget_monthly` is already expressed). Deterministic — no AI call."""
    budget = budget_monthly if budget_monthly is not None else (
        getattr(profile, "budget_monthly", None) if profile else None)
    size = household_size if household_size is not None else default_household_size(profile)
    size = max(1, int(size or 1))
    rate = fx.eur_rate(currency)  # units of `currency` per 1 EUR

    ev = cached_breakdown(db, place.id)
    # A row produced by an older prompt version (e.g. before the rent/buy split) is treated as
    # pending so the page regenerates it on demand, rather than computing from stale fields.
    fresh = ev is not None and _fresh(ev, _fp(), 0)
    annual = budget * 12 if budget else None
    base: dict = {
        "pending": not fresh,
        "currency": currency,
        "budget_monthly": budget,
        "household_size": size,
        "annual_income": annual,
        "income_pathways": income_pathways(db, place.id, annual, lang, rate=rate),
    }
    if not fresh:
        return base

    comps = (ev.meta or {}).get("components") or {}
    notes = (ev.meta or {}).get("notes") or {}
    breakdown = []
    cost_total = 0.0
    # Housing slot follows the user's tenure (mortgage for buyers, rent otherwise) — see
    # _display_components. The breakdown row's key carries the chosen housing kind so the UI labels
    # it correctly ("Rent" vs "Mortgage").
    for c in _display_components(getattr(profile, "tenure", None) if profile else None):
        single_eur = float(comps.get(c) or 0)
        amount = round(single_eur * household_factor(c, size) * rate)
        cost_total += amount
        note = notes.get(c) or {}
        row = {
            "key": c, "single": round(single_eur * rate), "amount": amount,
            "note_fr": note.get("fr") or "", "note_en": note.get("en") or "",
        }
        # Housing carries the bedroom count it was sized for, so the UI can explain the figure
        # ("3-bedroom for a household of 4") rather than show an unexplained multiple.
        if c in ("rent", "buy"):
            row["bedrooms"] = bedrooms_for_size(size)
        breakdown.append(row)
    cost_total = round(cost_total)

    surplus = (budget - cost_total) if budget is not None else None
    ratio = (budget / cost_total) if (budget and cost_total > 0) else None
    base.update({
        "breakdown": breakdown,
        "cost_total": cost_total,
        "surplus": surplus,
        "ratio": round(ratio, 2) if ratio is not None else None,
        "verdict": _verdict(ratio) if ratio is not None else None,
        "summary_fr": ev.summary_fr or "",
        "summary_en": ev.summary_en or "",
        "sources": ev.sources or [],
    })
    return base
