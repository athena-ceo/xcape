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
from app.schemas.search import AddCandidateRequest, AddCriterionRequest, CandidateOut

router = APIRouter()


def _owned(db: Session, user: User, search_id: int) -> Search:
    search = db.get(Search, search_id)
    if search is None or search.user_id != user.id:
        raise HTTPException(status_code=404, detail="Search not found")
    return search


@router.get("/{search_id}/candidates", response_model=list[CandidateOut])
def list_candidates(
    search_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _owned(db, user, search_id)
    return (
        db.query(Candidate)
        .filter(Candidate.search_id == search_id, Candidate.status == "active")
        .order_by(Candidate.match_score.desc().nullslast())
        .all()
    )


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
        # TODO(ai): on miss, call services.place_research.research_place(name) and cache it.
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found (AI research not yet wired)")

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

    candidate = Candidate(search_id=search_id, place_id=place.id, per_criterion=place.attributes or {})
    db.add(candidate)
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
        per = dict(cand.per_criterion or {})
        per.setdefault(body.key, attrs.get(body.key))
        cand.per_criterion = per
    db.commit()
    for cand in candidates:
        db.refresh(cand)
    return candidates
