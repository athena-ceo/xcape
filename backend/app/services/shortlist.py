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
    "safety": {"high": 1.0, "medium": 0.55, "low": 0.15},
    "political_stability": {"high": 1.0, "medium": 0.55, "low": 0.15},
    "tax": {"low": 1.0, "medium": 0.6, "high": 0.3},
    "visa": {"easy": 1.0, "medium": 0.6, "hard": 0.25},
    "language_ease": {"french": 1.0, "english": 0.9, "easy": 0.75, "medium": 0.55, "hard": 0.3},
    "expat_community": {"large": 1.0, "medium": 0.6, "small": 0.3},
    "nature": {"high": 1.0, "medium": 0.6, "low": 0.3},
    "internet": {"fast": 1.0, "ok": 0.6, "slow": 0.3},
}

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
    if profile.criteria_weights:
        for key, value in profile.criteria_weights.items():
            weights[key] = float(value)
    return weights


def _criterion_value(key: str, attrs: dict, profile: Profile | None) -> float:
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
        # Otherwise fall back to how learnable the language is (static proxy), softened
        # if the user is willing to learn.
        base = _SCALES["language_ease"].get(str(attrs.get(key, "")).lower(), 0.5)
        if willing:
            return min(1.0, base + 0.2)
        return round(base * 0.7, 3)
    scale = _SCALES.get(key, {})
    return scale.get(str(attrs.get(key, "")).lower(), 0.5)


def _score_place(place: Place, weights: dict[str, float], profile: Profile | None):
    attrs = place.attributes or {}
    total = wsum = 0.0
    contributions: list[tuple[str, float]] = []
    for key, weight in weights.items():
        if weight <= 0:
            continue
        val = _criterion_value(key, attrs, profile)
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


def build_instant_shortlist(db: Session, user: User, search: Search) -> list[Candidate]:
    profile = user.profile
    weights = _effective_weights(profile)

    countries = db.query(Place).filter(Place.kind == "country").all()
    scored = sorted(
        ((p, *_score_place(p, weights, profile)) for p in countries),
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
