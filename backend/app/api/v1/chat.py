# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.chat import ChatMessage
from app.models.search import Search
from app.models.user import User
from app.schemas.place import ChatOut, ChatRequest
from app.services import chat as chat_service

router = APIRouter()


def _owned(db: Session, user: User, search_id: int) -> Search:
    search = db.get(Search, search_id)
    if search is None or search.user_id != user.id:
        raise HTTPException(status_code=404, detail="Search not found")
    return search


@router.get("/{search_id}/chat", response_model=list[ChatOut])
def history(search_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _owned(db, user, search_id)
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.search_id == search_id)
        .order_by(ChatMessage.created_at)
        .all()
    )


@router.post("/{search_id}/chat")
def send(
    search_id: int,
    body: ChatRequest,
    place_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Chat with tool-calling. Returns the assistant reply and whether the assistant
    changed the search (so the frontend can re-read the board). `place_id` (optional) adds
    that country's drill-down details to the assistant's context — used by the detail page,
    sharing the same conversation thread as the comparison page."""
    search = _owned(db, user, search_id)
    msg, changed = chat_service.reply(db, user, search, body.message, place_id=place_id)
    return {"reply": msg.content, "changed": changed}
