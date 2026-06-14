# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import models so Alembic autogenerate + create_all see every table.
from app.models import (  # noqa: E402,F401
    ai_log,
    app_config,
    candidate,
    chat,
    custom_eval,
    media,
    place,
    profile,
    search,
    user,
)
