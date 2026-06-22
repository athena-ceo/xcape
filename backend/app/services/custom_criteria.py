# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Persistence of user-defined custom criteria across a user's searches.

A user's custom criteria (e.g. "IBM lab") belong to them, not to one search — so they're
mirrored onto the profile and merged into every search. Persona-generated criteria (marked
source="persona") are per-search (regenerated from the persona/communities) and are NOT
persisted here.
"""

from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.profile import Profile
from app.models.search import Search
from app.models.user import User

# Per-community safety criteria belong under the Safety & protection category, not "Your
# criteria". Newer ones carry category="protection"; older stored defs may not.
_COMMUNITY_PREFIX = "custom_safety_for_my_community"


def _persona_categories() -> dict[str, str]:
    """{criterion key: category} for every persona custom criterion that declares a category,
    so older stored defs (added before the category existed) can be re-filed under the right
    built-in category instead of 'Your criteria' (e.g. retiree's pension visa → Practical)."""
    from app.services import criteria  # avoid circular import at module load
    from app.services.criterion_eval import slugify

    out: dict[str, str] = {}
    for p in criteria.personas():
        for cc in p.get("custom_criteria", []):
            cat = cc.get("category")
            if not cat:
                continue
            for lbl_key in ("label_en", "label_fr", "label"):
                lbl = cc.get(lbl_key)
                if lbl:
                    out[slugify(lbl)] = cat
    return out


def heal_categories(db: Session, search: Search) -> None:
    """Self-heal stored custom-criteria defs: give per-community safety criteria the
    'protection' category, and re-file any other persona criterion under its registry category,
    when an older def is missing it — so they group with the right built-in category in the
    board and drill-down (not under 'Your criteria')."""
    persona_cats = _persona_categories()
    defs = list(search.custom_criteria or [])
    changed = False
    healed = []
    for c in defs:
        c = dict(c)
        key = c.get("key", "")
        if not c.get("category"):
            if key.startswith(_COMMUNITY_PREFIX):
                c["category"] = "protection"
                changed = True
            elif key in persona_cats:
                c["category"] = persona_cats[key]
                changed = True
        healed.append(c)
    if changed:
        search.custom_criteria = healed
        flag_modified(search, "custom_criteria")
        db.commit()


def _profile(db: Session, user: User) -> Profile:
    if user.profile is None:
        p = Profile(user_id=user.id)
        db.add(p)
        db.commit()
        db.refresh(p)
        return p
    return user.profile


def persist_to_profile(db: Session, user: User, defs: list[dict]) -> None:
    """Mirror the given (user-authored) custom-criteria defs onto the profile, deduped by key.
    Persona-generated defs (source=='persona') are skipped."""
    prof = _profile(db, user)
    existing = list(prof.custom_criteria or [])
    have = {c.get("key") for c in existing}
    changed = False
    for d in defs or []:
        k = d.get("key")
        if not k or k in have or d.get("source") == "persona":
            continue
        existing.append({key: d.get(key) for key in ("key", "label", "description", "weight", "min", "category") if d.get(key) is not None})
        have.add(k)
        changed = True
    if changed:
        prof.custom_criteria = existing
        db.commit()


def merge_into_search(db: Session, user: User, search: Search) -> None:
    """Ensure the search includes the user's persistent custom criteria (by key). Self-heals
    searches created before a criterion was added, and seeds brand-new searches."""
    prof = user.profile
    persistent = (prof.custom_criteria or []) if prof else []
    if not persistent:
        return
    defs = list(search.custom_criteria or [])
    have = {c.get("key") for c in defs}
    added: list[str] = []
    for d in persistent:
        k = d.get("key")
        if k and k not in have:
            defs.append(dict(d))
            have.add(k)
            added.append(k)
    if added:
        search.custom_criteria = defs
        search.criteria_set = list({*(search.criteria_set or []), *added})
        db.commit()
