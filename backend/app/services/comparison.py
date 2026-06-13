# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Compare candidates against the user's current country (the baseline).

For each ordinal criterion we say whether a candidate is "better", "worse" or "same"
relative to where the user lives now — so the table can show at a glance whether the
move improves each dimension. Climate has no inherent direction (it depends on the
user's preference) so it carries no delta.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.place import Place
from app.models.user import User
from app.services.shortlist import _SCALES  # ordinal scales: higher = better for the user


def criterion_delta(key: str, cand_value, base_value) -> str | None:
    scale = _SCALES.get(key)
    if not scale:
        return None
    cv = scale.get(str(cand_value).lower())
    bv = scale.get(str(base_value).lower())
    if cv is None or bv is None:
        return None
    if cv > bv:
        return "better"
    if cv < bv:
        return "worse"
    return "same"


def compute_deltas(cand_attrs: dict | None, base_attrs: dict | None) -> dict[str, str]:
    if not base_attrs:
        return {}
    out: dict[str, str] = {}
    cand_attrs = cand_attrs or {}
    for key in base_attrs:
        delta = criterion_delta(key, cand_attrs.get(key), base_attrs[key])
        if delta:
            out[key] = delta
    return out


def get_current_country_place(
    db: Session, user: User, *, research: bool = False
) -> Place | None:
    """Resolve the Place for the user's current country (the baseline).

    With research=False, only the built-in DB is consulted (fast path for listings).
    With research=True, an unknown country is researched via AI and cached.
    """
    name = (user.current_country or "France").strip()
    place = db.query(Place).filter(Place.kind == "country", Place.name.ilike(name)).first()
    if place is None and research:
        from app.services import ai_client, place_research

        try:
            place = place_research.research_place(db, name, user_id=user.id)
        except ai_client.AIUnavailable:
            place = None
    return place
