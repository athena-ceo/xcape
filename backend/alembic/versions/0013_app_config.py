# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""app_config table (editable reference data, e.g. the criteria registry)

Revision ID: 0013_app_config
Revises: 0012_custom_eval_score
Create Date: 2026-06-14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0013_app_config"
down_revision = "0012_custom_eval_score"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _has_table("app_config"):
        op.create_table(
            "app_config",
            sa.Column("key", sa.String(length=60), primary_key=True),
            sa.Column("value", sa.JSON(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=True),
        )


def downgrade() -> None:
    if _has_table("app_config"):
        op.drop_table("app_config")
