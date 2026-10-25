# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""retiree persona: climate weight 1.5 -> 3 (data only)

With healthcare at 6 + 6 ("Healthcare for retirees"), a climate weight of 1.5 barely
separated a warm Spain from a cool Netherlands for a retiree who asked for warmth; once the
visa fixes (0029) stopped separating EU countries, cool countries tied with the obvious ones.

Applies the edit to (1) the DB copy of the criteria registry, which prod reads instead of the
bundled criteria.json, and (2) retiree profiles still carrying the untouched persona default
`climate: 1.5` (a user who re-tuned it keeps their value). Idempotent. Downgrade is a no-op.

Revision ID: 0030_retiree_climate_weight
Revises: 0029_retiree_visa_weight
Create Date: 2026-10-25
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "0030_retiree_climate_weight"
down_revision = "0029_retiree_visa_weight"
branch_labels = None
depends_on = None

OLD, NEW = 1.5, 3.0


def _as_dict(value):
    if isinstance(value, str):
        return json.loads(value)
    return value


def upgrade() -> None:
    bind = op.get_bind()
    json_param = sa.bindparam("v", type_=sa.JSON)

    row = bind.execute(sa.text("select value from app_config where key = 'criteria'")).first()
    if row is not None and row[0]:
        reg = _as_dict(row[0])
        changed = False
        for p in reg.get("personas", []):
            weights = p.get("weights") or {}
            if p.get("key") == "retiree" and float(weights.get("climate", 0) or 0) == OLD:
                weights["climate"] = NEW
                changed = True
        if changed:
            bind.execute(
                sa.text("update app_config set value = :v where key = 'criteria'").bindparams(json_param),
                {"v": reg},
            )

    profiles = bind.execute(
        sa.text("select id, criteria_weights from profiles where persona = 'retiree'")
    ).fetchall()
    for pid, weights in profiles:
        weights = _as_dict(weights) or {}
        if float(weights.get("climate", 0) or 0) == OLD:
            weights["climate"] = NEW
            bind.execute(
                sa.text("update profiles set criteria_weights = :v where id = :id").bindparams(json_param),
                {"v": weights, "id": pid},
            )


def downgrade() -> None:
    pass
