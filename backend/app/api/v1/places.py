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
from pydantic import BaseModel

from app.schemas.place import MediaOut, PlaceOut
from app.services import ai_client, board, country_facts, criteria, criterion_eval, place_research

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


def _custom_defs_for(db: Session, user: User, search: int | None) -> list:
    if search is None:
        return []
    s = db.get(Search, search)
    return (s.custom_criteria or []) if (s is not None and s.user_id == user.id) else []


@router.get("/{place_id}/detail")
def get_detail(
    place_id: int,
    lang: str = "fr",
    search: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Per-criterion detail for the drill-down, assembled from caches — INSTANT, no AI call.
    Each row carries `pending: true` until its text exists; the page fills them progressively
    via POST /detail/generate. `lang` selects the language; `search` adds the custom criteria."""
    place = db.get(Place, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    custom_defs = _custom_defs_for(db, user, search)
    return {"criteria": board.criterion_details(db, place, user.profile, custom_defs, lang)}


class GenerateDetailRequest(BaseModel):
    keys: list[str]      # criteria to fill, in priority order (clicked → visible → rest)
    limit: int = 2       # how many AI generations to do this call (the page loops)


@router.post("/{place_id}/detail/generate")
def generate_detail(
    place_id: int,
    body: GenerateDetailRequest,
    lang: str = "fr",
    search: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate up to `limit` of the still-pending criteria in `keys` (in order), then return
    the freshly assembled detail. Objective/custom → criterion_eval; computed → per-key detail
    text; proximity is synthesised (skipped). The page calls this repeatedly until nothing is
    pending, so boxes fill in progressively."""
    place = db.get(Place, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    custom_defs = _custom_defs_for(db, user, search)

    defs = criteria.definitions(custom_defs)                 # objective + custom: {label, description}
    computed_text = set(criteria.computed_keys()) - {"proximity"}
    have_evals = set(criterion_eval.evals_for_place(db, place.id, list(defs.keys())).keys())
    have_detail = set(place_research.detail_map(place).keys())

    made = 0
    for key in body.keys:
        if made >= body.limit:
            break
        if key in defs:
            if key in have_evals:
                continue
            d = defs[key]
            if criterion_eval.evaluate(db, place, key, d["label"], d.get("description"), user_id=user.id):
                made += 1
        elif key in computed_text:
            if key in have_detail:
                continue
            if place_research.criterion_detail_one(db, place, key, user_id=user.id):
                made += 1
        # proximity / unknown keys: nothing to generate
    return {"criteria": board.criterion_details(db, place, user.profile, custom_defs, lang)}


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
