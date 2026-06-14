# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Instant, seed-driven shortlist — no AI call.

Scores every country Place against the user's profile so the first results appear with
zero latency. The score blends per-criterion quality with the user's stated priorities:

- baseline weights, overridden by the user's explicit criteria_weights;
- weight boosts derived from *why they are leaving* (so we avoid places with the same
  problem — e.g. leaving for political reasons up-weights political_stability);
- household adjustments (families care more about healthcare & safety);
- climate preference matching and language-learning willingness.

AI-based discrimination refines this list later (build phase 3).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.place import Place
from app.models.profile import Profile
from app.models.search import Search
from app.models.user import User

SHORTLIST_SIZE = 15
MAX_COMPARE = 5  # how many candidates can sit in the comparison board at once

# Ordinal scales: 0..1, higher is better for the user.
_SCALES: dict[str, dict[str, float]] = {
    "cost_of_living": {"low": 1.0, "medium": 0.55, "high": 0.2},
    "healthcare": {"strong": 1.0, "good": 0.7, "basic": 0.3},
    "education": {"strong": 1.0, "good": 0.7, "basic": 0.3},
    "safety": {"high": 1.0, "medium": 0.55, "low": 0.15},
    "political_stability": {"high": 1.0, "medium": 0.55, "low": 0.15},
    "tax": {"low": 1.0, "medium": 0.6, "high": 0.3},
    "visa": {"easy": 1.0, "medium": 0.6, "hard": 0.25},
    "language_ease": {"french": 1.0, "english": 0.9, "easy": 0.75, "medium": 0.55, "hard": 0.3},
    "expat_community": {"large": 1.0, "medium": 0.6, "small": 0.3},
    "nature": {"high": 1.0, "medium": 0.6, "low": 0.3},
    "internet": {"fast": 1.0, "ok": 0.6, "slow": 0.3},
}

# All criteria the UI can show / weight / filter on.
CRITERIA_KEYS = [
    "cost_of_living", "climate", "language_ease", "healthcare", "education", "safety",
    "political_stability", "tax", "visa", "expat_community", "nature", "internet",
]

_DEFAULT_WEIGHTS: dict[str, float] = {
    "cost_of_living": 1.0,
    "healthcare": 1.0,
    "safety": 1.0,
    "political_stability": 1.0,
    "language_ease": 0.8,
    "climate": 0.8,
    "tax": 0.5,
    "visa": 0.7,
}

# "Leaving because of X" → up-weight the criterion that avoids the same problem.
_REASON_BOOST: dict[str, dict[str, float]] = {
    "politics": {"political_stability": 1.5},
    "safety": {"safety": 1.5},
    "economy": {"cost_of_living": 1.0, "tax": 0.5},
    "cost": {"cost_of_living": 1.5},
    "climate": {"climate": 1.0},
    "healthcare": {"healthcare": 1.5},
    "career": {"internet": 0.3},
    "lifestyle": {"nature": 0.6, "climate": 0.4},
}

# Human-readable reason labels (FR/EN) for the criteria that drove a high score.
_REASON_LABELS: dict[str, dict[str, str]] = {
    "cost_of_living": {"fr": "coût de la vie abordable", "en": "affordable cost of living"},
    "healthcare": {"fr": "système de santé solide", "en": "strong healthcare"},
    "safety": {"fr": "sécurité élevée", "en": "high safety"},
    "political_stability": {"fr": "stabilité politique", "en": "political stability"},
    "tax": {"fr": "fiscalité douce", "en": "light taxation"},
    "visa": {"fr": "visa accessible", "en": "accessible visa"},
    "language_ease": {"fr": "langue accessible", "en": "manageable language"},
    "climate": {"fr": "climat qui vous convient", "en": "climate that suits you"},
    "expat_community": {"fr": "communauté d'expatriés", "en": "expat community"},
    "nature": {"fr": "nature et paysages", "en": "nature and landscapes"},
}


def _effective_weights(profile: Profile | None) -> dict[str, float]:
    weights = dict(_DEFAULT_WEIGHTS)
    if not profile:
        return weights
    for reason in profile.reasons_leaving or []:
        for key, boost in _REASON_BOOST.get(reason, {}).items():
            weights[key] = weights.get(key, 0.0) + boost
    if profile.household_type == "family":
        weights["healthcare"] = weights.get("healthcare", 0) + 0.5
        weights["safety"] = weights.get("safety", 0) + 0.5
    # Education only matters for families, or couples planning children. It is not in the
    # baseline weights, so singles / childless couples don't score on it at all.
    if profile.household_type == "family" or (
        profile.household_type == "couple" and getattr(profile, "intends_children", False)
    ):
        weights["education"] = weights.get("education", 0) + 1.5
    if profile.criteria_weights:
        for key, value in profile.criteria_weights.items():
            weights[key] = float(value)
    return weights


# EU/EEA + Switzerland — the freedom-of-movement zone: citizens of any of these can
# settle in any other with no visa. iso 3166-1 alpha-2.
_EU_FOM = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE",
    "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
    "IS", "LI", "NO", "CH",
}


def _single_citizenship_visa(citizenship: str, dest: str, base: float) -> float:
    """Ease of settling for ONE citizenship."""
    if dest and citizenship == dest:
        return 1.0  # citizen of the destination
    if dest in _EU_FOM:
        return 1.0 if citizenship in _EU_FOM else 0.3  # EU free movement, else hard
    return base


def _visa_value(attrs: dict, profile: Profile | None, place: Place | None) -> float:
    """Ease of moving the whole household there, given its citizenships (not residence).

    Uses the MOST RESTRICTIVE citizenship — everyone must be able to settle, so a French
    + American household is judged by the American passport, not the French one.
    """
    citz = (
        {str(c).upper() for c in (profile.user.citizenships or [])}
        if (profile and profile.user and profile.user.citizenships)
        else set()
    )
    base = _SCALES["visa"].get(str(attrs.get("visa", "")).lower(), 0.5)
    if not citz:
        return base  # citizenship unknown — fall back to general accessibility
    dest = (place.iso_code or "").upper() if place else ""
    return min(_single_citizenship_visa(c, dest, base) for c in citz)


# Coarse monthly cost of living for one person (EUR), by symbolic level — a proxy used
# to score affordability against the user's budget. The per-country AI drill-down gives
# real figures; this only needs to rank countries sensibly relative to a budget.
_COST_BAND = {"low": 1200, "medium": 2200, "high": 3500}
_HOUSEHOLD_FACTOR = {"single": 1.0, "couple": 1.6, "family": 2.4}


def _cost_value(attrs: dict, profile: Profile | None) -> float:
    """Affordability of the cost of living given the user's budget + household.

    With a budget set, score how comfortably it covers the estimated cost; without one,
    fall back to the plain symbolic scale (cheaper = better).
    """
    level = str(attrs.get("cost_of_living", "")).lower()
    budget = getattr(profile, "budget_monthly", None) if profile else None
    if budget and level in _COST_BAND:
        factor = _HOUSEHOLD_FACTOR.get(getattr(profile, "household_type", None), 1.3)
        estimate = _COST_BAND[level] * factor
        ratio = budget / estimate
        # ratio 0.5 (budget half the cost) -> 0; ratio 1.2 (comfortable surplus) -> 1.
        return max(0.0, min(1.0, (ratio - 0.5) / 0.7))
    return _SCALES["cost_of_living"].get(level, 0.5)


def _criterion_value(key: str, attrs: dict, profile: Profile | None, place: Place | None = None) -> float:
    if key == "visa":
        return _visa_value(attrs, profile, place)
    if key == "cost_of_living":
        return _cost_value(attrs, profile)
    if key == "climate":
        pref = profile.climate_pref if profile else None
        return 1.0 if (pref and attrs.get("climate") == pref) else 0.5
    if key == "language_ease":
        skills = (profile.language_skills or {}) if profile else {}
        known = {str(lang).lower() for lang in (skills.get("known") or [])}
        willing = bool(skills.get("willing_to_learn"))
        country_langs = {str(lang).lower() for lang in (attrs.get("languages") or [])}
        # You already speak a language used there — best possible fit.
        if known and country_langs and (known & country_langs):
            return 1.0
        # You don't speak any local language. Fall back to how learnable it is, softened
        # if willing to learn. Default to "hard" (0.3) when the difficulty is unknown —
        # an unknown language you don't speak shouldn't be treated as middling.
        base = _SCALES["language_ease"].get(str(attrs.get(key, "")).lower(), 0.3)
        if willing:
            return min(1.0, base + 0.2)
        return round(base * 0.7, 3)
    scale = _SCALES.get(key, {})
    return scale.get(str(attrs.get(key, "")).lower(), 0.5)


def quality_tier(value: float) -> str:
    """Map a 0-1 criterion value to a colour tier: good / ok / bad."""
    return "good" if value >= 0.7 else ("ok" if value >= 0.45 else "bad")


def candidate_quality(place: Place, profile: Profile | None) -> dict[str, str]:
    """Per-criterion colour tier for a place, from the user's perspective."""
    attrs = place.attributes or {}
    return {k: quality_tier(_criterion_value(k, attrs, profile, place)) for k in CRITERIA_KEYS}


def passes_filters(place: Place, profile: Profile | None) -> bool:
    """Hard constraints: a place must satisfy every active filter to qualify."""
    filters = (profile.filters or {}) if profile else {}
    attrs = place.attributes or {}
    for key, fval in filters.items():
        if fval in (None, "", False):
            continue
        if key == "language_ease":
            known = {str(x).lower() for x in (profile.language_skills or {}).get("known", [])}
            langs = {str(x).lower() for x in (attrs.get("languages") or [])}
            if not (known and langs and (known & langs)):
                return False
        elif key == "climate":
            if attrs.get("climate") != fval:
                return False
        elif key == "visa":
            if _visa_value(attrs, profile, place) < 0.9:
                return False
        elif key in _SCALES:
            scale = _SCALES[key]
            pv = scale.get(str(attrs.get(key, "")).lower())
            fv = scale.get(str(fval).lower())
            if pv is None or fv is None or pv < fv:
                return False
    return True


def _score_place(place: Place, weights: dict[str, float], profile: Profile | None):
    attrs = place.attributes or {}
    total = wsum = 0.0
    contributions: list[tuple[str, float]] = []
    for key, weight in weights.items():
        if weight <= 0:
            continue
        val = _criterion_value(key, attrs, profile, place)
        total += val * weight
        wsum += weight
        contributions.append((key, val * weight))
    score = round(100 * total / wsum, 1) if wsum else 0.0
    locale = "fr"
    if profile and profile.user:
        locale = profile.user.locale or "fr"
    top = sorted(contributions, key=lambda t: t[1], reverse=True)[:3]
    reasons = [
        _REASON_LABELS[k][locale]
        for k, v in top
        if k in _REASON_LABELS and _criterion_value(k, attrs, profile) >= 0.7
    ]
    return score, reasons


def rescore_candidates(db: Session, user: User, search: Search) -> list[Candidate]:
    """Recompute score/reasons/rank for a search's existing candidates against the
    current profile, preserving membership and selection. Used after profile edits.
    """
    profile = user.profile
    weights = _effective_weights(profile)
    candidates = (
        db.query(Candidate)
        .filter(Candidate.search_id == search.id, Candidate.status == "active")
        .all()
    )
    scorable = [c for c in candidates if c.place]
    for cand in scorable:
        score, reasons = _score_place(cand.place, weights, profile)
        cand.match_score = score
        cand.match_reasons = reasons
    for rank, cand in enumerate(
        sorted(scorable, key=lambda c: c.match_score or 0, reverse=True), start=1
    ):
        cand.rank = rank
    db.commit()
    for cand in candidates:
        db.refresh(cand)
    return candidates


def explain_candidate(user: User, candidate: Candidate) -> dict:
    """Break down how a candidate's score was derived: each weighted criterion's
    quality (0-100), its weight, and the contribution it adds to the final score.
    Contributions sum to the score.
    """
    profile = user.profile
    weights = _effective_weights(profile)
    place = candidate.place
    attrs = (place.attributes or {}) if place else {}
    prioritized = set((profile.criteria_weights or {}).keys()) if profile else set()

    active = {k: w for k, w in weights.items() if w > 0}
    wsum = sum(active.values())
    rows = []
    for key, weight in active.items():
        quality = _criterion_value(key, attrs, profile, place)
        rows.append({
            "key": key,
            "quality": round(quality * 100),       # how good this country is on this criterion
            "weight": round(weight, 2),            # how much the user cares
            "contribution": round(100 * quality * weight / wsum, 1) if wsum else 0,
            "prioritized": key in prioritized,
        })
    rows.sort(key=lambda r: r["contribution"], reverse=True)
    score = round(sum(r["contribution"] for r in rows), 1)
    return {"score": score, "weight_total": round(wsum, 2), "rows": rows}


def build_instant_shortlist(db: Session, user: User, search: Search) -> list[Candidate]:
    profile = user.profile
    weights = _effective_weights(profile)

    countries = db.query(Place).filter(Place.kind == "country").all()
    # Apply hard filters (e.g. "must speak a language I know"); if filters exclude
    # everything, fall back to the unfiltered pool so the user still sees options.
    qualified = [p for p in countries if passes_filters(p, profile)]
    pool = qualified or countries
    scored = sorted(
        ((p, *_score_place(p, weights, profile)) for p in pool),
        key=lambda t: t[1],
        reverse=True,
    )[:SHORTLIST_SIZE]

    db.query(Candidate).filter(Candidate.search_id == search.id).delete()

    candidates: list[Candidate] = []
    for rank, (place, score, reasons) in enumerate(scored, start=1):
        cand = Candidate(
            search_id=search.id,
            place_id=place.id,
            match_score=score,
            match_reasons=reasons,
            rank=rank,
            selected=rank <= MAX_COMPARE,  # default: top 5 pre-selected for comparison
            per_criterion=place.attributes or {},
        )
        db.add(cand)
        candidates.append(cand)
    db.commit()
    for cand in candidates:
        db.refresh(cand)
    return candidates
