# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add candidates.override (explicit user pin-in / banish-out)

Revision ID: 0018_candidate_override
Revises: 0017_profile_custom_criteria
Create Date: 2026-06-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0018_candidate_override"
down_revision = "0017_profile_custom_criteria"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column("candidates", "override"):
        op.add_column("candidates", sa.Column("override", sa.String(length=3), nullable=True))


def downgrade() -> None:
    if _has_column("candidates", "override"):
        op.drop_column("candidates", "override")
