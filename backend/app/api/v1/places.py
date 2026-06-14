# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.media import MediaAsset
from app.models.place import Place
from app.models.search import Search
from app.models.user import User
from app.schemas.place import MediaOut, PlaceOut
from app.services import ai_client, board, country_facts, place_research

router = APIRouter()


@router.get("", response_model=list[PlaceOut])
def list_places(
    kind: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Place).filter(Place.active.is_(True))  # deactivated places aren't offered
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
    search: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Uniform per-criterion detail for the drill-down: every criterion (built-in and the
    search's custom ones) carries a 0-100 score, a justification and sources, from a single
    code path. `lang` selects the justification language; `search` adds the custom criteria."""
    place = db.get(Place, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    try:
        legacy = place_research.fetch_criteria_detail(db, place, lang=lang, user_id=user.id)
    except ai_client.AIUnavailable:
        legacy = {"criteria": []}

    custom_defs: list = []
    if search is not None:
        s = db.get(Search, search)
        if s is not None and s.user_id == user.id:
            custom_defs = s.custom_criteria or []
    return {"criteria": board.criterion_details(db, place, user.profile, custom_defs, lang, legacy)}


@router.get("/{place_id}/media", response_model=list[MediaOut])
def get_media(place_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    place = db.get(Place, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    existing = db.query(MediaAsset).filter(MediaAsset.place_id == place_id).all()
    if not existing:
        # Cache miss — discover media via web search (best-effort).
        try:
            existing = place_research.fetch_media(db, place, user_id=user.id)
        except ai_client.AIUnavailable:
            return []
    # De-duplicate by URL (older rows may contain dupes with differing titles).
    seen: set[str] = set()
    unique = []
    for m in existing:
        nu = place_research.normalize_url(m.url)
        if nu not in seen:
            seen.add(nu)
            unique.append(m)
    return unique
