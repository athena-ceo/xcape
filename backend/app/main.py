# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import settings

app = FastAPI(title="xCape API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [
        "https://xcape.athenadecisions.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "environment": settings.environment}
