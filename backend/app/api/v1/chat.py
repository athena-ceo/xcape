# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
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


@router.post("/{search_id}/chat", response_model=ChatOut)
def send(
    search_id: int,
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    search = _owned(db, user, search_id)
    return chat_service.reply(db, user, search, body.message)


@router.post("/{search_id}/chat/stream")
def send_stream(
    search_id: int,
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Streaming chat: plain-text chunks as the answer is generated."""
    search = _owned(db, user, search_id)
    return StreamingResponse(
        chat_service.reply_stream(db, user, search, body.message),
        media_type="text/plain; charset=utf-8",
    )
