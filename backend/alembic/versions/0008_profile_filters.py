# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add profiles.filters

Revision ID: 0008_profile_filters
Revises: 0007_user_citizenships
Create Date: 2026-06-14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0008_profile_filters"
down_revision = "0007_user_citizenships"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column("profiles", "filters"):
        op.add_column("profiles", sa.Column("filters", sa.JSON(), nullable=True))


def downgrade() -> None:
    if _has_column("profiles", "filters"):
        op.drop_column("profiles", "filters")
