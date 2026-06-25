# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Pre-compute the golden-visa finder's pathways for every country.

The per-country drill-down evaluates visa pathways on-demand, but the finder ranks ACROSS all
countries, so it needs the investment / retirement / digital-nomad pathways cached up front.
This populates them (cross-user cache, shared with the drill-down). Cache-first and resumable:
re-run to continue; `--force` re-evaluates, `--limit N` caps the AI calls this run.

Usage: python -m app.db.evaluate_visas [--force] [--limit N]
Invoked by `./xcape.sh evaluate-visas <env>`.
"""

from __future__ import annotations

import sys

from app.db.session import SessionLocal
from app.models.place import Place
from app.services import ai_client, visa_pathways


def main() -> None:
    force = "--force" in sys.argv
    limit = None
    for i, a in enumerate(sys.argv):
        if a == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])

    db = SessionLocal()
    try:
        places = db.query(Place).filter(Place.kind == "country", Place.active.is_(True)).all()
        cats = visa_pathways.FINDER_CATEGORIES
        print(f"Evaluating {len(cats)} finder pathways ({', '.join(cats)}) across {len(places)} "
              f"countries (force={force}, limit={limit}). Cache-first, resumable.")
        made = 0
        for place in places:
            for cat in cats:
                if limit is not None and made >= limit:
                    print(f"Hit limit ({limit}).")
                    print(f"Done. {made} pathway evaluations this run.")
                    return
                before = visa_pathways.cached_rows(db, place.id).get(cat)
                before_fp = before.prompt_fp if before is not None else None
                try:
                    ev = visa_pathways.evaluate_pathway(db, place, cat, force=force)
                except ai_client.AIUnavailable:
                    print("AI unavailable (no API key) — stopping (re-run later to resume).")
                    print(f"Done. {made} pathway evaluations this run.")
                    return
                except Exception as e:  # never let one cell kill a long unattended run
                    db.rollback()
                    print(f"  skip {place.name}/visa_{cat}: {type(e).__name__}: {e}")
                    continue
                if ev is not None and ev.prompt_fp != before_fp:
                    made += 1
        print(f"Done. {made} pathway evaluations this run.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
