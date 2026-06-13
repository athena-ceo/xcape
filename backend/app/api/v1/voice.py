# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.deps import get_current_user
from app.models.user import User
from app.services import ai_client

router = APIRouter()


@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Transcribe spoken input (mobile-friendly) to text via the AI provider."""
    data = await audio.read()
    text = ai_client.transcribe_audio(data, filename=audio.filename or "audio.webm", user_id=user.id)
    return {"text": text}
