# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add profiles.minority_groups

Revision ID: 0010_profile_minority_groups
Revises: 0009_profile_intends_children
Create Date: 2026-06-14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0010_profile_minority_groups"
down_revision = "0009_profile_intends_children"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column("profiles", "minority_groups"):
        op.add_column("profiles", sa.Column("minority_groups", sa.JSON(), nullable=True))


def downgrade() -> None:
    if _has_column("profiles", "minority_groups"):
        op.drop_column("profiles", "minority_groups")
