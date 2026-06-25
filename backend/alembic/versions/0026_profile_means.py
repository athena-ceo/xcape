# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add profiles.annual_income + investable_amount (residency-by-means criteria)

Revision ID: 0026_profile_means
Revises: 0025_user_heritages
Create Date: 2026-06-25
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0026_profile_means"
down_revision = "0025_user_heritages"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    for col in ("annual_income", "investable_amount"):
        if not _has_column("profiles", col):
            op.add_column("profiles", sa.Column(col, sa.Integer(), nullable=True))


def downgrade() -> None:
    for col in ("annual_income", "investable_amount"):
        if _has_column("profiles", col):
            op.drop_column("profiles", col)
