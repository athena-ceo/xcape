# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Progressively AI-evaluate every objective criterion for every country (cross-user cache).

Fills the per-(country, criterion) eval cache so the ~190 seed-sparse countries get real
scores + justifications instead of clustering at neutral. Cache-first and resumable: re-run
to continue; pass --force to refresh, --stale-days N to refresh evals older than N days.

Usage: python -m app.db.evaluate_all [--force] [--stale-days N] [--limit N]
Invoked by `./xcape.sh evaluate-all <env>`.
"""

from __future__ import annotations

import sys

from app.db.session import SessionLocal
from app.models.place import Place
from app.services import ai_client, criteria, criterion_eval


def main() -> None:
    force = "--force" in sys.argv
    stale_days = 0
    limit = None
    for i, a in enumerate(sys.argv):
        if a == "--stale-days" and i + 1 < len(sys.argv):
            stale_days = int(sys.argv[i + 1])
        if a == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])

    db = SessionLocal()
    try:
        places = db.query(Place).filter(Place.kind == "country").all()
        keys = criteria.OBJECTIVE_KEYS
        print(f"Evaluating {len(keys)} objective criteria across {len(places)} countries "
              f"(force={force}, stale_days={stale_days}, limit={limit}). Cache-first, resumable.")
        try:
            # Commit per cell (inside evaluate) → safe to interrupt and resume.
            made = criterion_eval.populate(
                db, places, keys, stale_days=stale_days, force=force, limit=limit
            )
        except ai_client.AIUnavailable:
            print("AI unavailable (no API key) — nothing to do.")
            return
        print(f"Done. {made} new evaluations this run.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
