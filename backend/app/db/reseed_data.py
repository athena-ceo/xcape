# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Force-refresh the country data (places + cached criterion evals) from the bundled seed
files, OVERWRITING existing rows.

`seed` / `deploy` are insert-only (bootstrap + new countries, never clobber), so this is how
you push committed data updates — refreshed evals (`evaluate-all` → `export-evals` → commit)
or corrected place attributes — onto an environment. Only touches the seeded 217 countries'
built-in criteria; user-defined custom-criterion evals, searches and profiles are untouched.
Run via `./xcape.sh reseed-data <dev|prod>`.
"""

from __future__ import annotations

from app.db.seed import seed
from app.db.session import SessionLocal


def main() -> None:
    db = SessionLocal()
    try:
        n = seed(db, overwrite=True)
        print(f"Re-seeded {n} places and refreshed cached evals (overwrite).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
