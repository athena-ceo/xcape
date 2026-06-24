# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add ai_query_logs.result_summary (AI return-value summary)

Revision ID: 0024_ai_log_result_summary
Revises: 0023_user_active
Create Date: 2026-06-24
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0024_ai_log_result_summary"
down_revision = "0023_user_active"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column("ai_query_logs", "result_summary"):
        op.add_column("ai_query_logs", sa.Column("result_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    if _has_column("ai_query_logs", "result_summary"):
        op.drop_column("ai_query_logs", "result_summary")
