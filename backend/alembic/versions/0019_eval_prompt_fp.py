# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add place_custom_evals.prompt_fp (prompt fingerprint → cache invalidation)

Revision ID: 0019_eval_prompt_fp
Revises: 0018_candidate_override
Create Date: 2026-06-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0019_eval_prompt_fp"
down_revision = "0018_candidate_override"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column("place_custom_evals", "prompt_fp"):
        op.add_column("place_custom_evals", sa.Column("prompt_fp", sa.String(length=16), nullable=True))
        op.create_index("ix_place_custom_evals_prompt_fp", "place_custom_evals", ["prompt_fp"])


def downgrade() -> None:
    if _has_column("place_custom_evals", "prompt_fp"):
        op.drop_index("ix_place_custom_evals_prompt_fp", table_name="place_custom_evals")
        op.drop_column("place_custom_evals", "prompt_fp")
