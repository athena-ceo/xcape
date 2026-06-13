# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""add places.facts and places.criteria_detail

Revision ID: 0006_place_detail
Revises: 0005_candidate_selected
Create Date: 2026-06-14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0006_place_detail"
down_revision = "0005_candidate_selected"
branch_labels = None
depends_on = None

_COLUMNS = ("facts", "criteria_detail")


def _existing(table: str) -> set[str]:
    return {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    have = _existing("places")
    for name in _COLUMNS:
        if name not in have:
            op.add_column("places", sa.Column(name, sa.JSON(), nullable=True))


def downgrade() -> None:
    have = _existing("places")
    for name in _COLUMNS:
        if name in have:
            op.drop_column("places", name)
