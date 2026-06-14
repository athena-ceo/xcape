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
from app.models.profile import Profile
from app.models.user import User
from app.services import criteria


def criterion_delta(key: str, cand_value, base_value) -> str | None:
    scale = criteria.scales().get(key)
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


def criterion_reason(place: Place, profile: Profile | None, key: str) -> dict:
    """A structured, user-relative justification for a criterion cell. Returns a code +
    tokens; the frontend renders the localized sentence (keeps wording in i18n)."""
    from app.services import shortlist  # avoid circular import at module load

    attrs = place.attributes or {}
    val = attrs.get(key)

    if key == "language_ease":
        skills = (profile.language_skills or {}) if profile else {}
        known = {str(x).lower() for x in (skills.get("known") or [])}
        langs = [str(x) for x in (attrs.get("languages") or [])]
        matched = [l for l in langs if l.lower() in known]
        if matched:
            return {"code": "lang_known", "lang": matched[0]}
        if skills.get("willing_to_learn"):
            return {"code": "lang_willing", "langs": langs}
        return {"code": "lang_none", "langs": langs}

    if key == "visa":
        citz = {str(c).upper() for c in (profile.user.citizenships or [])} if (
            profile and profile.user and profile.user.citizenships) else set()
        dest = (place.iso_code or "").upper()
        if not citz:
            return {"code": "visa_level", "v": val}
        if dest and dest in citz:
            return {"code": "visa_citizen"}
        if dest in shortlist._EU_FOM:
            return {"code": "visa_free"} if all(c in shortlist._EU_FOM for c in citz) \
                else {"code": "visa_restricted"}
        return {"code": "visa_level", "v": val}

    if key == "cost_of_living":
        budget = getattr(profile, "budget_monthly", None) if profile else None
        band = shortlist._COST_BAND.get(str(val).lower())
        if budget and band:
            factor = shortlist._HOUSEHOLD_FACTOR.get(getattr(profile, "household_type", None), 1.3)
            ratio = budget / (band * factor)
            code = "cost_within" if ratio >= 1.0 else "cost_tight" if ratio >= 0.8 else "cost_over"
            return {"code": code, "v": val}
        return {"code": "cost_level", "v": val}

    if key == "climate":
        pref = profile.climate_pref if profile else None
        return {"code": "climate_match" if (pref and val == pref) else "climate_diff", "v": val}

    if key == "inclusion":
        groups = (getattr(profile, "minority_groups", None) or []) if profile else []
        acceptance = attrs.get("social_acceptance") or {}
        openness = attrs.get("openness")
        if groups:
            openness_v = shortlist._OPENNESS_SCALE.get(str(openness).lower(), 0.5)
            # Name the limiting (worst-accepted) community so the user sees what drove it.
            worst = min(
                groups,
                key=lambda g: shortlist._GROUP_SCALE.get(str(acceptance.get(g, "")).lower(), openness_v),
            )
            # Free-text / not-yet-assessed communities have no specific level → use openness.
            return {"code": "inclusion_groups", "group": worst,
                    "v": acceptance.get(worst) or openness}
        return {"code": "inclusion_general", "v": openness}

    return {"code": "level", "v": val}


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
