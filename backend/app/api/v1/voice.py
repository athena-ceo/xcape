# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import ai_client

router = APIRouter()


@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Transcribe spoken input (mobile-friendly) to text via the AI provider."""
    data = await audio.read()
    try:
        text = ai_client.transcribe_audio(
            data, filename=audio.filename or "audio.webm", db=db, user_id=user.id
        )
    except ai_client.AIUnavailable:
        raise HTTPException(status_code=503, detail="Voice transcription unavailable")
    return {"text": text}
