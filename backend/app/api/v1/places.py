# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.media import MediaAsset
from app.models.place import Place
from app.models.user import User
from app.schemas.place import MediaOut, PlaceOut
from app.services import ai_client, place_research

router = APIRouter()


@router.get("", response_model=list[PlaceOut])
def list_places(
    kind: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Place)
    if kind:
        q = q.filter(Place.kind == kind)
    return q.order_by(Place.name).all()


@router.get("/{place_id}", response_model=PlaceOut)
def get_place(place_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    place = db.get(Place, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return place


@router.get("/{place_id}/media", response_model=list[MediaOut])
def get_media(place_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    place = db.get(Place, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    existing = db.query(MediaAsset).filter(MediaAsset.place_id == place_id).all()
    if existing:
        return existing
    # Cache miss — discover media via web search (best-effort).
    try:
        return place_research.fetch_media(db, place, user_id=user.id)
    except ai_client.AIUnavailable:
        return []
