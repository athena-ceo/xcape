# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add users.ancestry_countries (declared ancestry-based visa eligibility)

Revision ID: 0021_user_ancestry
Revises: 0020_eval_meta
Create Date: 2026-06-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0021_user_ancestry"
down_revision = "0020_eval_meta"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column("users", "ancestry_countries"):
        op.add_column("users", sa.Column("ancestry_countries", sa.JSON(), nullable=True))


def downgrade() -> None:
    if _has_column("users", "ancestry_countries"):
        op.drop_column("users", "ancestry_countries")
