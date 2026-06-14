# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Account-level operations shared by the user (self-service) and admin endpoints."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.search import Search
from app.models.user import User


def reset_user_data(db: Session, user: User) -> None:
    """Wipe a user's relocation data so they can start over from a blank questionnaire:
    delete all their searches (ORM-cascades candidates + chat messages + custom criteria)
    and their profile. Keeps the account itself (email, password, citizenships). The shared
    cross-user evaluation cache is untouched."""
    for search in db.query(Search).filter(Search.user_id == user.id).all():
        db.delete(search)  # cascades candidates and chat messages
    if user.profile is not None:
        db.delete(user.profile)
    db.commit()
