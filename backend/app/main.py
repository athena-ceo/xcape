# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.core.config import settings
from app.services import errors

app = FastAPI(title="xCape API", version="0.1.0")


@app.exception_handler(Exception)
async def record_unhandled(request: Request, exc: Exception):
    """Any unhandled exception → a row in the admin "Errors" tab, then a plain 500.
    (Starlette still re-raises afterwards, so the traceback also reaches the container log.)"""
    await run_in_threadpool(
        errors.record_exception, exc, source="request",
        method=request.method, path=request.url.path,
        user_id=errors.user_id_from_auth(request.headers.get("authorization")),
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "environment": settings.environment}
