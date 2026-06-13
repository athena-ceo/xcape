# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add user first_name, last_name, current_country

Revision ID: 0004_user_identity
Revises: 0003_media_source_text
Create Date: 2026-06-14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0004_user_identity"
down_revision = "0003_media_source_text"
branch_labels = None
depends_on = None

_COLUMNS = {
    "first_name": sa.String(length=120),
    "last_name": sa.String(length=120),
    "current_country": sa.String(length=120),
}


def _existing(table: str) -> set[str]:
    return {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    have = _existing("users")
    for name, type_ in _COLUMNS.items():
        if name not in have:
            op.add_column("users", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    have = _existing("users")
    for name in _COLUMNS:
        if name in have:
            op.drop_column("users", name)
