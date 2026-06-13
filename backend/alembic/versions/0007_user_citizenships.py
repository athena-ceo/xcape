# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add users.citizenships

Revision ID: 0007_user_citizenships
Revises: 0006_place_detail
Create Date: 2026-06-14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0007_user_citizenships"
down_revision = "0006_place_detail"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column("users", "citizenships"):
        op.add_column("users", sa.Column("citizenships", sa.JSON(), nullable=True))


def downgrade() -> None:
    if _has_column("users", "citizenships"):
        op.drop_column("users", "citizenships")
