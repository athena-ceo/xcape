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

from app.models.profile import Profile
from app.models.search import Search
from app.models.user import User


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
