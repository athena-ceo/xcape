# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-13

Squashed initial: creates the full schema from the ORM metadata. Subsequent changes
MUST use `alembic revision --autogenerate` with idempotent guards (see CLAUDE.md).
"""
from alembic import op

from app.db.base import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
