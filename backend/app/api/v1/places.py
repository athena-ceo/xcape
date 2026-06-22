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
from app.services import (
    ai_client, board, country_facts, criteria, criterion_eval, place_research, visa_pathways,
)

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


def _visa_panel(db: Session, place: Place, user: User, lang: str) -> dict:
    """Assemble the visa-pathways panel: the categories relevant to this user for this place,
    each cached row's terms (or pending), and the best (easiest existing) pathway."""
    profile = user.profile
    cats = visa_pathways.relevant_categories(profile, place)
    rows = visa_pathways.cached_rows(db, place.id)
    out = []
    best_cat, best_diff = None, -1
    for c in cats:
        entry = {"category": c, "label": visa_pathways.category_label(c, lang)}
        ev = rows.get(c)
        if ev is None:
            entry["pending"] = True
        else:
            entry["pending"] = False
            entry.update(visa_pathways.pathway_payload(ev, lang))
            if entry.get("exists") and (entry.get("difficulty") or 0) > best_diff:
                best_cat, best_diff = c, entry.get("difficulty") or 0
        out.append(entry)
    return {"categories": out, "best": best_cat}


@router.get("/{place_id}/visa-pathways")
def get_visa_pathways(
    place_id: int,
    lang: str = "fr",
    search: int | None = None,  # accepted for symmetry with the drill-down; profile drives relevance
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The visa-pathways panel for the drill-down — INSTANT, from cache. Categories relevant to
    the user (persona + declared ancestry + universal) come back with their terms or `pending:true`;
    the page fills pending ones via POST .../visa-pathways/generate."""
    place = db.get(Place, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return _visa_panel(db, place, user, lang)


class GenerateVisaRequest(BaseModel):
    limit: int = 2  # how many pathway categories to evaluate this call (the page loops)


@router.post("/{place_id}/visa-pathways/generate")
def generate_visa_pathways(
    place_id: int,
    body: GenerateVisaRequest,
    lang: str = "fr",
    search: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Evaluate up to `limit` of the still-pending relevant pathway categories on-demand, then
    return the assembled panel. Called repeatedly so pathways fill in progressively."""
    place = db.get(Place, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    cats = visa_pathways.relevant_categories(user.profile, place)
    have = visa_pathways.cached_rows(db, place.id)
    pending = [c for c in cats if c not in have]
    visa_pathways.ensure_for_place(db, place, pending[: max(0, body.limit)], user_id=user.id)
    return _visa_panel(db, place, user, lang)


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
