# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add candidates.match_reasons

Revision ID: 0002_candidate_match_reasons
Revises: 0001_initial
Create Date: 2026-06-13
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0002_candidate_match_reasons"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return any(c["name"] == column for c in inspect(bind).get_columns(table))


def upgrade() -> None:
    if not _has_column("candidates", "match_reasons"):
        op.add_column("candidates", sa.Column("match_reasons", sa.JSON(), nullable=True))


def downgrade() -> None:
    if _has_column("candidates", "match_reasons"):
        op.drop_column("candidates", "match_reasons")
