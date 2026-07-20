# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add users.family_countries (locations to stay near → family_proximity criterion)

Revision ID: 0027_user_family_countries
Revises: 0026_profile_means
Create Date: 2026-07-20
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0027_user_family_countries"
down_revision = "0026_profile_means"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column("users", "family_countries"):
        op.add_column(
            "users",
            sa.Column("family_countries", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    if _has_column("users", "family_countries"):
        op.drop_column("users", "family_countries")
