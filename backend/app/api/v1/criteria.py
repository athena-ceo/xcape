# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.user import User
from app.services import criteria as criteria_service

router = APIRouter()


@router.get("")
def get_criteria(_: User = Depends(get_current_user)):
    """The criteria registry (tree, tags, reasons, communities) — the single catalog the
    frontend renders, so the UI reflects whatever the registry (later: admin) defines."""
    return criteria_service.raw()
