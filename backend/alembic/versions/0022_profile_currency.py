# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add profiles.currency (per-user budgeting currency)

Revision ID: 0022_profile_currency
Revises: 0021_user_ancestry
Create Date: 2026-06-22
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0022_profile_currency"
down_revision = "0021_user_ancestry"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column("profiles", "currency"):
        op.add_column("profiles", sa.Column("currency", sa.String(length=3), nullable=True))


def downgrade() -> None:
    if _has_column("profiles", "currency"):
        op.drop_column("profiles", "currency")
