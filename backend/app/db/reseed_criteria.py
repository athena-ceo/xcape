# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Refresh the editable criteria registry (criteria tree, personas, communities) in
app_config from the bundled `criteria.json`.

Unlike `seed`, which leaves an existing registry untouched (to preserve admin edits), this
OVERWRITES the stored registry with the file version — used to roll out registry changes
(e.g. new personas/communities) to an environment. Any admin edits made through the UI are
replaced. Run via `./xcape.sh reseed-criteria <dev|prod>`.
"""

from __future__ import annotations

from app.db.session import SessionLocal
from app.models.app_config import AppConfig
from app.services import criteria


def reseed_criteria() -> dict:
    """Overwrite app_config['criteria'] with the bundled file registry. Returns a small
    counts dict (nodes/personas/communities) as a sanity signal."""
    db = SessionLocal()
    try:
        registry = criteria.file_registry()
        row = db.get(AppConfig, "criteria")
        if row is None:
            db.add(AppConfig(key="criteria", value=registry))
        else:
            row.value = registry
        db.commit()
        criteria.invalidate()
        return {k: len(registry.get(k, [])) for k in ("nodes", "personas", "communities")}
    finally:
        db.close()


def main() -> None:
    counts = reseed_criteria()
    print(
        "Criteria registry refreshed from bundled file "
        f"({counts['nodes']} nodes, {counts['personas']} personas, "
        f"{counts['communities']} communities)."
    )


if __name__ == "__main__":
    main()
