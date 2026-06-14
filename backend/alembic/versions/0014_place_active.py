# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add places.active (deactivate instead of delete)

Revision ID: 0014_place_active
Revises: 0013_app_config
Create Date: 2026-06-14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0014_place_active"
down_revision = "0013_app_config"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column("places", "active"):
        op.add_column("places", sa.Column("active", sa.Boolean(), nullable=False,
                                          server_default=sa.true()))


def downgrade() -> None:
    if _has_column("places", "active"):
        op.drop_column("places", "active")
