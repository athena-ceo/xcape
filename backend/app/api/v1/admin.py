# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.security import hash_password
from app.db.session import get_db
from app.models.ai_log import AIQueryLog
from app.models.place import Place
from app.models.search import Search
from app.models.user import User
from app.schemas.auth import AdminPasswordReset, UserOut
from app.schemas.place import PlaceOut
from app.schemas.search import SearchOut

router = APIRouter()


@router.post("/users/{user_id}/reset-password", status_code=204)
def reset_password(
    user_id: int,
    body: AdminPasswordReset,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin sets a new password for any user."""
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    target.password_hash = hash_password(body.password)
    db.commit()


@router.get("/users", response_model=list[UserOut])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(User).order_by(User.created_at.desc()).all()


@router.get("/searches", response_model=list[SearchOut])
def list_searches(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(Search).order_by(Search.updated_at.desc()).limit(500).all()


@router.get("/places", response_model=list[PlaceOut])
def list_places(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(Place).order_by(Place.name).all()


@router.get("/ai-log")
def ai_log(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.query(AIQueryLog).order_by(AIQueryLog.created_at.desc()).limit(500).all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "kind": r.kind,
            "model": r.model,
            "tokens_in": r.tokens_in,
            "tokens_out": r.tokens_out,
            "latency_ms": r.latency_ms,
            "cost_estimate": r.cost_estimate,
            "created_at": r.created_at,
        }
        for r in rows
    ]
