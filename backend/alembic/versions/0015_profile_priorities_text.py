# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add profiles.priorities_text (free-text priorities)

Revision ID: 0015_profile_priorities_text
Revises: 0014_place_active
Create Date: 2026-06-14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0015_profile_priorities_text"
down_revision = "0014_place_active"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column("profiles", "priorities_text"):
        op.add_column("profiles", sa.Column("priorities_text", sa.Text(), nullable=True))


def downgrade() -> None:
    if _has_column("profiles", "priorities_text"):
        op.drop_column("profiles", "priorities_text")
