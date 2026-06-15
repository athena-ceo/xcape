# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add profiles.persona (relocation archetype)

Revision ID: 0016_profile_persona
Revises: 0015_profile_priorities_text
Create Date: 2026-06-15
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0016_profile_persona"
down_revision = "0015_profile_priorities_text"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column("profiles", "persona"):
        op.add_column("profiles", sa.Column("persona", sa.String(length=40), nullable=True))


def downgrade() -> None:
    if _has_column("profiles", "persona"):
        op.drop_column("profiles", "persona")
