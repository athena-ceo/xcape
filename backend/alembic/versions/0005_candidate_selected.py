# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add candidates.selected

Revision ID: 0005_candidate_selected
Revises: 0004_user_identity
Create Date: 2026-06-14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0005_candidate_selected"
down_revision = "0004_user_identity"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column("candidates", "selected"):
        op.add_column(
            "candidates",
            sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    if _has_column("candidates", "selected"):
        op.drop_column("candidates", "selected")
