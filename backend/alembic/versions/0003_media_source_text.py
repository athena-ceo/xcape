# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""widen media_assets.source to Text

Revision ID: 0003_media_source_text
Revises: 0002_candidate_match_reasons
Create Date: 2026-06-13
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0003_media_source_text"
down_revision = "0002_candidate_match_reasons"
branch_labels = None
depends_on = None


def _source_type(table: str, column: str):
    bind = op.get_bind()
    for c in inspect(bind).get_columns(table):
        if c["name"] == column:
            return c["type"]
    return None


def upgrade() -> None:
    col = _source_type("media_assets", "source")
    if col is not None and not isinstance(col, sa.Text):
        op.alter_column("media_assets", "source", type_=sa.Text(), existing_nullable=True)


def downgrade() -> None:
    op.alter_column(
        "media_assets", "source", type_=sa.String(length=120), existing_nullable=True
    )
