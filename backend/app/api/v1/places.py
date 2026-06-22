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
    affordability, ai_client, board, country_facts, criteria, criterion_eval, place_research,
    visa_pathways,
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
    force: bool = False  # admin only: regenerate even criteria that already have cached text


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
    pending, so boxes fill in progressively.

    `force` (admins only) regenerates each listed criterion even when it already has cached text —
    this is the per-country "regenerate text" action, used e.g. after a prompt change."""
    if body.force and not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
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
            if key in have_evals and not body.force:
                continue
            d = defs[key]
            if criterion_eval.evaluate(db, place, key, d["label"], d.get("description"),
                                       user_id=user.id, force=body.force):
                made += 1
        elif key in computed_text:
            if key in have_detail and not body.force:
                continue
            if place_research.criterion_detail_one(db, place, key, user_id=user.id, force=body.force):
                made += 1
        # proximity / unknown keys: nothing to generate
    return {"criteria": board.criterion_details(db, place, user.profile, custom_defs, lang)}


def _visa_panel(db: Session, place: Place, user: User, lang: str) -> dict:
    """Assemble the visa-pathways panel: the categories relevant to this user for this place,
    each cached row's terms (or pending).

    We deliberately do NOT crown a single "best route": program difficulty is generic, while
    actual eligibility depends on personal circumstances we haven't validated (a family route
    needs relatives there; an ancestry route needs a declared tie). The panel presents the
    candidate routes; the user judges which they qualify for."""
    profile = user.profile
    cats = visa_pathways.relevant_categories(profile, place)
    rows = visa_pathways.cached_rows(db, place.id)
    out = []
    for c in cats:
        entry = {"category": c, "label": visa_pathways.category_label(c, lang)}
        ev = rows.get(c)
        if ev is None:
            entry["pending"] = True
        else:
            entry["pending"] = False
            entry.update(visa_pathways.pathway_payload(ev, lang))
        out.append(entry)
    return {"categories": out, "best": None}


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
    force: bool = False  # admin only: re-evaluate even categories already cached
    categories: list[str] | None = None  # explicit set to (re)evaluate; default = the pending ones


@router.post("/{place_id}/visa-pathways/generate")
def generate_visa_pathways(
    place_id: int,
    body: GenerateVisaRequest,
    lang: str = "fr",
    search: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Evaluate up to `limit` of the relevant pathway categories on-demand, then return the
    assembled panel. Called repeatedly so pathways fill in progressively. By default only the
    still-pending categories are evaluated; admins can pass `force` (with an explicit `categories`
    chunk) to re-research even cached ones — the per-country "regenerate" action."""
    if body.force and not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    place = db.get(Place, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    cats = visa_pathways.relevant_categories(user.profile, place)
    if body.categories is not None:
        targets = [c for c in body.categories if c in cats]
    else:
        have = visa_pathways.cached_rows(db, place.id)
        targets = [c for c in cats if c not in have]
    visa_pathways.ensure_for_place(
        db, place, targets[: max(0, body.limit)], force=body.force, user_id=user.id)
    return _visa_panel(db, place, user, lang)


@router.get("/{place_id}/affordability")
def get_affordability(
    place_id: int,
    lang: str = "fr",
    budget: int | None = None,      # editable override; falls back to the profile budget
    household: int | None = None,   # editable override; falls back to the persona household size
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The budget / affordability calculator for the drill-down — INSTANT, from cache. Returns the
    cost-vs-budget verdict + breakdown when the country's cost breakdown is cached, else
    `pending:true` (fill it via POST .../affordability/generate). The visa income tie-in uses
    whatever income-based pathways are already cached."""
    place = db.get(Place, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return affordability.compute(
        db, place, user.profile, budget_monthly=budget, household_size=household, lang=lang)


class GenerateAffordabilityRequest(BaseModel):
    budget: int | None = None
    household: int | None = None
    force: bool = False  # admin only: re-research even a cached breakdown


@router.post("/{place_id}/affordability/generate")
def generate_affordability(
    place_id: int,
    body: GenerateAffordabilityRequest,
    lang: str = "fr",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate the country's cost breakdown on-demand (one AI call, cached + shared), and ensure
    the income-based visa pathways are evaluated so the income tie-in is populated. Admins can pass
    `force` to re-research a cached breakdown (the per-country "regenerate" action). Returns the
    assembled calculator payload."""
    if body.force and not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    place = db.get(Place, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    affordability.evaluate_breakdown(db, place, force=body.force, user_id=user.id)
    # Populate the income-based routes the tie-in checks (always cache-first — the visa panel /
    # the visa regenerate flow own pathway freshness, so we don't re-force them here).
    relevant = set(visa_pathways.relevant_categories(user.profile, place))
    visa_pathways.ensure_for_place(
        db, place, [c for c in affordability.INCOME_CATEGORIES if c in relevant], user_id=user.id)
    return affordability.compute(
        db, place, user.profile, budget_monthly=body.budget, household_size=body.household, lang=lang)


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
