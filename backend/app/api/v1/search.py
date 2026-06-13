# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.search import Search
from app.models.user import User
from app.schemas.search import CandidateOut, SearchCreate, SearchOut, SearchUpdate
from app.services import shortlist as shortlist_service

router = APIRouter()


def _owned(db: Session, user: User, search_id: int) -> Search:
    search = db.get(Search, search_id)
    if search is None or search.user_id != user.id:
        raise HTTPException(status_code=404, detail="Search not found")
    return search


@router.get("", response_model=list[SearchOut])
def list_searches(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Search).filter(Search.user_id == user.id).order_by(Search.updated_at.desc()).all()


@router.post("", response_model=SearchOut, status_code=201)
def create_search(
    body: SearchCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    search = Search(user_id=user.id, title=body.title)
    db.add(search)
    db.commit()
    db.refresh(search)
    return search


@router.get("/{search_id}", response_model=SearchOut)
def get_search(search_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _owned(db, user, search_id)


@router.patch("/{search_id}", response_model=SearchOut)
def update_search(
    search_id: int,
    body: SearchUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    search = _owned(db, user, search_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(search, field, value)
    db.commit()
    db.refresh(search)
    return search


@router.post("/{search_id}/shortlist", response_model=list[CandidateOut])
def build_shortlist(
    search_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Instant, seed-driven shortlist of 10-20 countries from the built-in database.

    No AI call — ranks Place rows against the user's profile weights.
    """
    search = _owned(db, user, search_id)
    return shortlist_service.build_instant_shortlist(db, user, search)
