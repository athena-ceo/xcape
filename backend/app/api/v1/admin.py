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
from app.models.candidate import Candidate
from app.schemas.auth import AdminPasswordReset, UserOut

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


@router.get("/searches")
def list_searches(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    """All users' searches with who owns them and how many candidates they hold."""
    rows = db.query(Search).order_by(Search.updated_at.desc()).limit(500).all()
    out = []
    for s in rows:
        active = [c for c in s.candidates if c.status == "active"]
        out.append({
            "id": s.id,
            "user_email": s.user.email if s.user else None,
            "title": s.title,
            "candidates": len(active),
            "selected": sum(1 for c in active if c.selected),
            "updated_at": s.updated_at,
        })
    return out


@router.get("/places")
def list_places(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    """The place database with data provenance & freshness, so admins can see which
    countries are still seed-only vs AI-enriched."""
    rows = db.query(Place).order_by(Place.name).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "kind": p.kind,
            "iso_code": p.iso_code,
            "source": p.source,
            "enriched": bool(p.source == "ai" or p.facts or p.criteria_detail),
            "freshness_at": p.freshness_at,
        }
        for p in rows
    ]


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
