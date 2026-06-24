# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add users.is_active (admin soft-disable)

Revision ID: 0023_user_active
Revises: 0022_profile_currency
Create Date: 2026-06-24
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0023_user_active"
down_revision = "0022_profile_currency"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column("users", "is_active"):
        op.add_column(
            "users",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        )


def downgrade() -> None:
    if _has_column("users", "is_active"):
        op.drop_column("users", "is_active")
