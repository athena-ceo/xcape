# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""The user's hearted countries — a personal shelf across searches (emotional layer)."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.emotion import Heart
from app.models.place import Place
from app.models.user import User

router = APIRouter()


@router.get("")
def list_hearts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Hearted countries, most recent first."""
    rows = (
        db.query(Heart).filter(Heart.user_id == user.id)
        .order_by(Heart.created_at.desc(), Heart.id.desc()).all()
    )
    return [{"place_id": h.place_id, "name": h.place.name, "iso_code": h.place.iso_code,
             "created_at": h.created_at} for h in rows if h.place]


@router.put("/{place_id}", status_code=204)
def add_heart(place_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Heart a country (idempotent)."""
    if db.get(Place, place_id) is None:
        raise HTTPException(status_code=404, detail="Place not found")
    if not db.query(Heart).filter_by(user_id=user.id, place_id=place_id).first():
        db.add(Heart(user_id=user.id, place_id=place_id))
        try:
            db.commit()
        except IntegrityError:  # double tap: the other request hearted it first
            db.rollback()
    return Response(status_code=204)


@router.delete("/{place_id}", status_code=204)
def remove_heart(place_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Un-heart a country (idempotent)."""
    db.query(Heart).filter_by(user_id=user.id, place_id=place_id).delete()
    db.commit()
    return Response(status_code=204)
