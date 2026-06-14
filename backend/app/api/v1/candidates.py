# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.candidate import Candidate
from app.models.place import Place
from app.models.search import Search
from app.models.user import User
from app.schemas.search import (
    AddCandidateRequest,
    AddCriterionRequest,
    CandidateOut,
    SetSelectedRequest,
)
from app.services import ai_client, comparison, place_research
from app.services import shortlist as shortlist_service
from app.services.shortlist import MAX_COMPARE

router = APIRouter()


def _owned(db: Session, user: User, search_id: int) -> Search:
    search = db.get(Search, search_id)
    if search is None or search.user_id != user.id:
        raise HTTPException(status_code=404, detail="Search not found")
    return search


def _selected_count(db: Session, search_id: int, exclude_id: int | None = None) -> int:
    q = db.query(Candidate).filter(
        Candidate.search_id == search_id,
        Candidate.status == "active",
        Candidate.selected.is_(True),
    )
    if exclude_id is not None:
        q = q.filter(Candidate.id != exclude_id)
    return q.count()


@router.get("/{search_id}/candidates", response_model=list[CandidateOut])
def list_candidates(
    search_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _owned(db, user, search_id)
    candidates = (
        db.query(Candidate)
        .filter(Candidate.search_id == search_id, Candidate.status == "active")
        .order_by(Candidate.match_score.desc().nullslast())
        .all()
    )
    # Annotate each candidate with how it compares to the user's current country
    # (fast path: baseline must already be in the DB; France is seeded).
    baseline = comparison.get_current_country_place(db, user, research=False)
    base_attrs = baseline.attributes if baseline else None

    # Language is judged by whether the user can communicate (their known languages),
    # so the arrow stays consistent with the displayed languages.
    profile = user.profile
    known = {
        str(lang).lower()
        for lang in ((profile.language_skills or {}).get("known") or [] if profile else [])
    }
    base_langs = {str(lang).lower() for lang in ((base_attrs or {}).get("languages") or [])}

    for cand in candidates:
        cand.vs_current = comparison.compute_deltas(cand.per_criterion, base_attrs)
        if cand.place:
            cand.quality = shortlist_service.candidate_quality(cand.place, profile)
            cand.reasons = {
                k: comparison.criterion_reason(cand.place, profile, k)
                for k in shortlist_service.CRITERIA_KEYS
            }
        if known:
            # Read languages from the live place so existing searches benefit without
            # needing the shortlist rebuilt.
            place_attrs = cand.place.attributes if cand.place else (cand.per_criterion or {})
            cand_langs = {str(lang).lower() for lang in (place_attrs.get("languages") or [])}
            cand_ok, base_ok = bool(known & cand_langs), bool(known & base_langs)
            cand.vs_current["language_ease"] = (
                "same" if cand_ok == base_ok else ("better" if cand_ok else "worse")
            )
    return candidates


@router.post("/{search_id}/candidates", response_model=CandidateOut, status_code=201)
def add_candidate(
    search_id: int,
    body: AddCandidateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _owned(db, user, search_id)
    place: Place | None = None
    if body.place_id is not None:
        place = db.get(Place, body.place_id)
    elif body.place_name:
        place = db.query(Place).filter(Place.name.ilike(body.place_name)).first()
        if place is None:
            # Not in the built-in DB — research it on demand and cache it.
            try:
                place = place_research.research_place(db, body.place_name, user_id=user.id)
            except ai_client.AIUnavailable:
                raise HTTPException(
                    status_code=503, detail="AI research unavailable (no API key configured)"
                )
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")

    existing = (
        db.query(Candidate)
        .filter(Candidate.search_id == search_id, Candidate.place_id == place.id)
        .first()
    )
    if existing:
        existing.status = "active"
        db.commit()
        db.refresh(existing)
        return existing

    # A freshly added country joins the comparison if there's still room (<= 5).
    candidate = Candidate(
        search_id=search_id,
        place_id=place.id,
        per_criterion=place.attributes or {},
        selected=_selected_count(db, search_id) < MAX_COMPARE,
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


@router.get("/{search_id}/candidates/{candidate_id}/explanation")
def explain(
    search_id: int,
    candidate_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """How this candidate's score was derived (per-criterion value × weight)."""
    _owned(db, user, search_id)
    candidate = db.get(Candidate, candidate_id)
    if candidate is None or candidate.search_id != search_id:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return shortlist_service.explain_candidate(user, candidate)


@router.patch("/{search_id}/candidates/{candidate_id}", response_model=CandidateOut)
def set_selected(
    search_id: int,
    candidate_id: int,
    body: SetSelectedRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Select / unselect a candidate for the comparison board (server enforces max 5)."""
    _owned(db, user, search_id)
    candidate = db.get(Candidate, candidate_id)
    if candidate is None or candidate.search_id != search_id:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if body.selected and not candidate.selected:
        if _selected_count(db, search_id, exclude_id=candidate_id) >= MAX_COMPARE:
            raise HTTPException(
                status_code=409, detail=f"At most {MAX_COMPARE} countries can be compared"
            )
    candidate.selected = body.selected
    db.commit()
    db.refresh(candidate)
    return candidate


@router.delete("/{search_id}/candidates/{candidate_id}", status_code=204)
def remove_candidate(
    search_id: int,
    candidate_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _owned(db, user, search_id)
    candidate = db.get(Candidate, candidate_id)
    if candidate is None or candidate.search_id != search_id:
        raise HTTPException(status_code=404, detail="Candidate not found")
    candidate.status = "removed"
    db.commit()


@router.post("/{search_id}/criteria", response_model=list[CandidateOut])
def add_criterion(
    search_id: int,
    body: AddCriterionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a new criterion column; it fans out to every active candidate.

    Values present in seed attributes are copied immediately; missing ones are left
    null and filled later by AI research (see services.place_research).
    """
    search = _owned(db, user, search_id)
    if body.key not in (search.criteria_set or []):
        search.criteria_set = [*(search.criteria_set or []), body.key]

    candidates = (
        db.query(Candidate)
        .filter(Candidate.search_id == search_id, Candidate.status == "active")
        .all()
    )
    for cand in candidates:
        attrs = cand.place.attributes or {}
        value = attrs.get(body.key)
        if value is None:
            # Not in seed data — research this single attribute via AI (best-effort).
            try:
                value = place_research.fill_criterion(db, cand.place, body.key, user_id=user.id)
            except ai_client.AIUnavailable:
                value = None
        per = dict(cand.per_criterion or {})
        per[body.key] = value
        cand.per_criterion = per
    db.commit()
    for cand in candidates:
        db.refresh(cand)
    return candidates
