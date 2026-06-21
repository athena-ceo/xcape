# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add place_custom_evals.meta (structured trend fields)

Revision ID: 0020_eval_meta
Revises: 0019_eval_prompt_fp
Create Date: 2026-06-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0020_eval_meta"
down_revision = "0019_eval_prompt_fp"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column("place_custom_evals", "meta"):
        op.add_column("place_custom_evals", sa.Column("meta", sa.JSON(), nullable=True))


def downgrade() -> None:
    if _has_column("place_custom_evals", "meta"):
        op.drop_column("place_custom_evals", "meta")
