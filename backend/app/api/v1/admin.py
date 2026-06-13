# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.ai_log import AIQueryLog
from app.models.place import Place
from app.models.search import Search
from app.models.user import User
from app.schemas.auth import UserOut
from app.schemas.place import PlaceOut
from app.schemas.search import SearchOut

router = APIRouter()


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
