# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Instant, seed-driven shortlist — no AI call.

Scores every country Place against the user's profile weights so the first results
appear with zero latency. AI-based discrimination refines this list later.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.place import Place
from app.models.search import Search
from app.models.user import User

SHORTLIST_SIZE = 15

# Ordinal scales: higher is better for the user. Used to turn seed labels into points.
_SCALES: dict[str, dict[str, float]] = {
    "cost_of_living": {"low": 1.0, "medium": 0.6, "high": 0.2},
    "healthcare": {"strong": 1.0, "good": 0.7, "basic": 0.3},
    "safety": {"high": 1.0, "medium": 0.6, "low": 0.2},
    "political_stability": {"high": 1.0, "medium": 0.6, "low": 0.2},
    "language_ease": {"english": 1.0, "easy": 0.9, "medium": 0.6, "hard": 0.3},
}

_DEFAULT_WEIGHTS = {
    "cost_of_living": 1.0,
    "healthcare": 1.0,
    "safety": 1.0,
    "political_stability": 1.0,
    "language_ease": 0.8,
    "climate": 0.8,
}


def _score_place(place: Place, weights: dict[str, float], climate_pref: str | None) -> float:
    attrs = place.attributes or {}
    total = 0.0
    wsum = 0.0
    for key, weight in weights.items():
        if weight <= 0:
            continue
        if key == "climate":
            val = 1.0 if (climate_pref and attrs.get("climate") == climate_pref) else 0.5
        else:
            scale = _SCALES.get(key, {})
            val = scale.get(str(attrs.get(key, "")).lower(), 0.5)
        total += val * weight
        wsum += weight
    return round(100 * total / wsum, 1) if wsum else 0.0


def build_instant_shortlist(db: Session, user: User, search: Search) -> list[Candidate]:
    profile = user.profile
    weights = dict(_DEFAULT_WEIGHTS)
    if profile and profile.criteria_weights:
        weights.update({k: float(v) for k, v in profile.criteria_weights.items()})
    climate_pref = profile.climate_pref if profile else None

    countries = db.query(Place).filter(Place.kind == "country").all()
    scored = sorted(
        ((p, _score_place(p, weights, climate_pref)) for p in countries),
        key=lambda t: t[1],
        reverse=True,
    )[:SHORTLIST_SIZE]

    # Reset existing auto-shortlist candidates for a clean rebuild.
    db.query(Candidate).filter(Candidate.search_id == search.id).delete()

    candidates: list[Candidate] = []
    for rank, (place, score) in enumerate(scored, start=1):
        cand = Candidate(
            search_id=search.id,
            place_id=place.id,
            match_score=score,
            rank=rank,
            per_criterion=place.attributes or {},
        )
        db.add(cand)
        candidates.append(cand)
    db.commit()
    for cand in candidates:
        db.refresh(cand)
    return candidates
