# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""user-defined criteria: searches.custom_criteria + place_custom_evals

Revision ID: 0011_custom_criteria
Revises: 0010_profile_minority_groups
Create Date: 2026-06-14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0011_custom_criteria"
down_revision = "0010_profile_minority_groups"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def _has_table(table: str) -> bool:
    return inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _has_column("searches", "custom_criteria"):
        op.add_column("searches", sa.Column("custom_criteria", sa.JSON(), nullable=True))

    if not _has_table("place_custom_evals"):
        op.create_table(
            "place_custom_evals",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "place_id", sa.Integer(),
                sa.ForeignKey("places.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("key", sa.String(length=80), nullable=False),
            sa.Column("label", sa.String(length=160), nullable=False),
            sa.Column("level", sa.String(length=10), nullable=False),
            sa.Column("summary_fr", sa.String(), nullable=True),
            sa.Column("summary_en", sa.String(), nullable=True),
            sa.Column("sources", sa.JSON(), nullable=True),
            sa.Column(
                "freshness_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=True,
            ),
            sa.UniqueConstraint("place_id", "key", name="uq_custom_eval_place_key"),
        )
        op.create_index(
            "ix_place_custom_evals_place_id", "place_custom_evals", ["place_id"]
        )
        op.create_index("ix_place_custom_evals_key", "place_custom_evals", ["key"])


def downgrade() -> None:
    if _has_table("place_custom_evals"):
        op.drop_table("place_custom_evals")
    if _has_column("searches", "custom_criteria"):
        op.drop_column("searches", "custom_criteria")
