# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add profiles.custom_criteria (persistent user-defined criteria)

Revision ID: 0017_profile_custom_criteria
Revises: 0016_profile_persona
Create Date: 2026-06-15
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0017_profile_custom_criteria"
down_revision = "0016_profile_persona"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column("profiles", "custom_criteria"):
        op.add_column("profiles", sa.Column("custom_criteria", sa.JSON(), nullable=True))


def downgrade() -> None:
    if _has_column("profiles", "custom_criteria"):
        op.drop_column("profiles", "custom_criteria")
