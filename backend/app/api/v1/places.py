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
from app.services import ai_client, country_facts, place_research

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


@router.get("/{place_id}/facts")
def get_facts(place_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Basic country facts for the drill-down (fast; cached restcountries + Wikipedia)."""
    place = db.get(Place, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return country_facts.get_facts(db, place)


@router.get("/{place_id}/detail")
def get_detail(
    place_id: int,
    lang: str = "fr",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AI per-criterion detailed summary with sources (cached per language)."""
    place = db.get(Place, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    try:
        return place_research.fetch_criteria_detail(db, place, lang=lang, user_id=user.id)
    except ai_client.AIUnavailable:
        return {"criteria": []}


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
