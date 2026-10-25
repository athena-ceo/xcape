# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add app_errors table + ai_query_logs.status/error (failures surfaced in admin)

Revision ID: 0028_app_errors
Revises: 0027_user_family_countries
Create Date: 2026-10-25
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0028_app_errors"
down_revision = "0027_user_family_countries"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return inspect(op.get_bind()).has_table(table)


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def _has_index(table: str, name: str) -> bool:
    return any(i["name"] == name for i in inspect(op.get_bind()).get_indexes(table))


def upgrade() -> None:
    if not _has_column("ai_query_logs", "status"):
        op.add_column("ai_query_logs", sa.Column("status", sa.String(10), nullable=True))
    if not _has_column("ai_query_logs", "error"):
        op.add_column("ai_query_logs", sa.Column("error", sa.Text(), nullable=True))

    if not _has_table("app_errors"):
        op.create_table(
            "app_errors",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("source", sa.String(30), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("method", sa.String(10), nullable=True),
            sa.Column("path", sa.String(300), nullable=True),
            sa.Column("error_type", sa.String(120), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("detail", sa.Text(), nullable=True),
        )
    if not _has_index("app_errors", "ix_app_errors_created_at"):
        op.create_index("ix_app_errors_created_at", "app_errors", ["created_at"])
    if not _has_index("app_errors", "ix_app_errors_source"):
        op.create_index("ix_app_errors_source", "app_errors", ["source"])


def downgrade() -> None:
    if _has_table("app_errors"):
        op.drop_table("app_errors")
    if _has_column("ai_query_logs", "error"):
        op.drop_column("ai_query_logs", "error")
    if _has_column("ai_query_logs", "status"):
        op.drop_column("ai_query_logs", "status")
