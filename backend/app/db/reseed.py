# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Reload the committed seed into the DB, OVERWRITING existing rows.

`seed` / `deploy` are insert-only (bootstrap + new countries, never clobber), so this is how you
push committed data updates — refreshed attributes + evals from `generate --export` — onto an
environment. Only touches the seeded countries' built-in data; user searches/profiles and custom
criteria are untouched. `--criteria` also force-rolls the criteria registry (replacing admin UI
edits). Run via `./xcape.sh reseed <env> [--criteria]`.
"""

from __future__ import annotations

import sys

from app.db.seed import seed, seed_criteria
from app.db.session import SessionLocal


def main() -> None:
    db = SessionLocal()
    try:
        if "--criteria" in sys.argv:
            if seed_criteria(db, overwrite=True):
                print("Criteria registry refreshed from the bundled file.")
        n = seed(db, overwrite=True)
        print(f"Re-seeded {n} places and refreshed cached attributes + evals (overwrite).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
