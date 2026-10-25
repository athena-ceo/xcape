# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""emotional layer: hearts, postcards, profiles.story

Revision ID: 0031_emotion
Revises: 0030_retiree_climate_weight
Create Date: 2026-10-25
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0031_emotion"
down_revision = "0030_retiree_climate_weight"
branch_labels = None
depends_on = None


def _insp():
    return inspect(op.get_bind())


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in _insp().get_columns(table))


def upgrade() -> None:
    if not _has_column("profiles", "story"):
        op.add_column("profiles", sa.Column("story", sa.JSON(), nullable=True))

    if not _insp().has_table("hearts"):
        op.create_table(
            "hearts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("place_id", sa.Integer(), sa.ForeignKey("places.id", ondelete="CASCADE"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("user_id", "place_id", name="uq_heart_user_place"),
        )
        op.create_index("ix_hearts_user_id", "hearts", ["user_id"])

    if not _insp().has_table("postcards"):
        op.create_table(
            "postcards",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("place_id", sa.Integer(), sa.ForeignKey("places.id", ondelete="CASCADE"), nullable=False),
            sa.Column("lang", sa.String(2), nullable=False),
            sa.Column("fingerprint", sa.String(16), nullable=False),
            sa.Column("setting", sa.String(120), nullable=True),
            sa.Column("postcard", sa.Text(), nullable=False),
            sa.Column("premortem", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("user_id", "place_id", "lang", name="uq_postcard_user_place_lang"),
        )
        op.create_index("ix_postcards_user_id", "postcards", ["user_id"])


def downgrade() -> None:
    if _insp().has_table("postcards"):
        op.drop_table("postcards")
    if _insp().has_table("hearts"):
        op.drop_table("hearts")
    if _has_column("profiles", "story"):
        op.drop_column("profiles", "story")
