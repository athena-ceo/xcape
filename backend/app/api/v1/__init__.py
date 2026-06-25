# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from fastapi import APIRouter

from app.api.v1 import (
    admin, auth, candidates, chat, criteria, persona, places, profile, search, visa, voice,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(profile.router, prefix="/profile", tags=["profile"])
api_router.include_router(search.router, prefix="/searches", tags=["search"])
api_router.include_router(candidates.router, prefix="/searches", tags=["candidates"])
api_router.include_router(chat.router, prefix="/searches", tags=["chat"])
api_router.include_router(places.router, prefix="/places", tags=["places"])
api_router.include_router(visa.router, prefix="/visa", tags=["visa"])
api_router.include_router(criteria.router, prefix="/criteria", tags=["criteria"])
api_router.include_router(persona.router, prefix="/persona", tags=["persona"])
api_router.include_router(voice.router, prefix="/voice", tags=["voice"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
