# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add users.heritages (ethno-religious heritage → right-of-return pathways)

Revision ID: 0025_user_heritages
Revises: 0024_ai_log_result_summary
Create Date: 2026-06-25
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0025_user_heritages"
down_revision = "0024_ai_log_result_summary"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column("users", "heritages"):
        op.add_column(
            "users",
            sa.Column("heritages", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    if _has_column("users", "heritages"):
        op.drop_column("users", "heritages")
