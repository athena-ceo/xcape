# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Record server-side failures to `app_errors` so they surface in the admin "Errors" tab.

Each row is written in its OWN session: the caller's session may be the one that just
failed (or be mid-transaction), and recording must never break — nor roll back — the
request that is reporting it. Recording never raises.
"""

from __future__ import annotations

import logging
import traceback

from app.db.session import SessionLocal
from app.models.app_error import AppError

logger = logging.getLogger(__name__)

# Indirection so tests can point recording at their in-memory database.
_session_factory = SessionLocal

# Set on an exception once recorded, so a failure that bubbles up through several layers
# (AI client → chat → request handler) shows up once, at the most specific layer.
_RECORDED = "_xcape_error_recorded"


def record(
    *,
    source: str,
    error_type: str,
    message: str,
    detail: str | None = None,
    user_id: int | None = None,
    method: str | None = None,
    path: str | None = None,
) -> None:
    try:
        db = _session_factory()
        try:
            db.add(AppError(
                source=source[:30], error_type=(error_type or "Error")[:120],
                message=(message or "")[:2000], detail=(detail or None) and detail[-8000:],
                user_id=user_id, method=(method or None) and method[:10],
                path=(path or None) and path[:300],
            ))
            db.commit()
        finally:
            db.close()
    except Exception:  # recording must never break the caller
        logger.exception("could not record app error (%s: %s)", error_type, message)


def record_exception(exc: BaseException, *, source: str, message: str | None = None, **ctx) -> None:
    """Record `exc` (with its traceback) unless a deeper layer already recorded it."""
    if getattr(exc, _RECORDED, False):
        return
    record(
        source=source,
        error_type=type(exc).__name__,
        message=message or str(exc) or type(exc).__name__,
        detail="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        **ctx,
    )
    try:
        setattr(exc, _RECORDED, True)
    except Exception:  # some exception types refuse attributes; worst case it's recorded twice
        pass


def user_id_from_auth(authorization: str | None) -> int | None:
    """Best-effort user id from a `Bearer <jwt>` header, for error context only."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        from app.core.security import decode_token

        return int(decode_token(authorization.split(" ", 1)[1]).get("sub"))
    except Exception:
        return None
