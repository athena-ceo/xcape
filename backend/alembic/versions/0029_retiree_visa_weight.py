# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
"""retiree persona: stop counting visa ease twice (data only)

The retiree persona weighted the generic `visa` criterion 5 AND added a "Retirement visa"
criterion at 6 — the same question twice, plus residency-by-income/investment: ~40% of the
score was immigration ease, so retiree-visa programmes (Mauritius, Uruguay, Panama) beat
Portugal/Spain/France for everyone. The persona's `visa` weight drops to 2.0 (= the
priority weight the profile page applies) and "Retirement visa" is flagged `mobility` (moot
when the household can settle freely).

Applies the same edit to (1) the DB copy of the criteria registry, which prod reads instead
of the bundled criteria.json, and (2) retiree profiles still carrying the untouched persona
default `visa: 5`. Idempotent. Downgrade is a no-op (a user may have re-tuned since).

Revision ID: 0029_retiree_visa_weight
Revises: 0028_app_errors
Create Date: 2026-10-25
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "0029_retiree_visa_weight"
down_revision = "0028_app_errors"
branch_labels = None
depends_on = None

OLD_VISA, NEW_VISA = 5.0, 2.0


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
            if p.get("key") != "retiree":
                continue
            weights = p.get("weights") or {}
            if float(weights.get("visa", 0) or 0) == OLD_VISA:
                weights["visa"] = NEW_VISA
                changed = True
            for cc in p.get("custom_criteria", []):
                if cc.get("label_en") == "Retirement visa" and not cc.get("mobility"):
                    cc["mobility"] = True
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
        if float(weights.get("visa", 0) or 0) == OLD_VISA:
            weights["visa"] = NEW_VISA
            bind.execute(
                sa.text("update profiles set criteria_weights = :v where id = :id").bindparams(json_param),
                {"v": weights, "id": pid},
            )


def downgrade() -> None:
    pass
