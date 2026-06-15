# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.models.user import User
from app.services import criteria

router = APIRouter()


class DeriveRequest(BaseModel):
    reasons: list[str] = []
    priorities: list[str] = []


@router.post("/derive")
def derive(body: DeriveRequest, _: User = Depends(get_current_user)):
    """Rule-based persona derivation from the first onboarding answers. Returns the matched
    persona (key + its label/blurb/weights/ask/custom_criteria) so onboarding can confirm it,
    gate the remaining questions, and preview the focus criteria. Falls back to 'neutral'."""
    key = criteria.persona_for(body.reasons, body.priorities)
    return {"key": key, "persona": criteria.persona(key)}
