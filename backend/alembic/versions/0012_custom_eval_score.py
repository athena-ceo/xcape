# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add place_custom_evals.score

Revision ID: 0012_custom_eval_score
Revises: 0011_custom_criteria
Create Date: 2026-06-14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0012_custom_eval_score"
down_revision = "0011_custom_criteria"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column("place_custom_evals", "score"):
        op.add_column("place_custom_evals", sa.Column("score", sa.Integer(), nullable=True))


def downgrade() -> None:
    if _has_column("place_custom_evals", "score"):
        op.drop_column("place_custom_evals", "score")
