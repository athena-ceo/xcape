# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Merge duplicate country rows that share an ISO code (e.g. "Espagne" and "Spain", both ES).

Duplicates arose when a country was researched on-demand under a name that didn't match an
existing localized row (the lookup was name-based). The lookup now dedupes by ISO, so this is a
one-off cleanup for rows already created. For each ISO group it KEEPS one canonical row (prefer a
seeded/admin row over an AI-researched one, then the richest, then the oldest), moves any user
board entries (candidates) onto it, and deletes the duplicates — cascading their evals/media.

Usage: python -m app.db.dedupe_places [--dry-run]
Invoked by `./xcape.sh dedupe-places <env>`.
"""

from __future__ import annotations

import sys
from collections import defaultdict

from app.db.session import SessionLocal
from app.models.candidate import Candidate
from app.models.place import Place


def main() -> None:
    dry = "--dry-run" in sys.argv
    db = SessionLocal()
    try:
        rows = db.query(Place).filter(Place.kind == "country", Place.iso_code.isnot(None)).all()
        groups: dict[str, list[Place]] = defaultdict(list)
        for p in rows:
            iso = (p.iso_code or "").upper().strip()
            if iso:
                groups[iso].append(p)

        dup_groups = {iso: ps for iso, ps in groups.items() if len(ps) > 1}
        if not dup_groups:
            print("No ISO-duplicate countries found.")
            return
        print(f"{len(dup_groups)} ISO(s) with duplicate country rows"
              + (" (dry run — no changes)" if dry else "") + ":")

        merged = 0
        for iso, ps in sorted(dup_groups.items()):
            # Canonical = a real seed/admin row first, then the richest (most attributes), then
            # the oldest id — so we keep curated data over an AI-guessed duplicate.
            ps.sort(key=lambda p: (p.source == "ai", -len(p.attributes or {}), p.id))
            primary, dups = ps[0], ps[1:]
            merge_list = ", ".join(f"'{d.name}' (id {d.id})" for d in dups)
            print(f"  {iso}: keep '{primary.name}' (id {primary.id}, source {primary.source}); "
                  f"merge {merge_list}")
            if dry:
                continue
            for dup in dups:
                # Move any board entries to the canonical row, unless that search already has it
                # (the unique (search_id, place_id) constraint) — then the dup's entry is dropped.
                for cand in db.query(Candidate).filter(Candidate.place_id == dup.id).all():
                    clash = (
                        db.query(Candidate)
                        .filter(Candidate.search_id == cand.search_id,
                                Candidate.place_id == primary.id)
                        .first()
                    )
                    if clash is None:
                        cand.place_id = primary.id
                    # else: leave it — deleting the dup cascade-removes this redundant candidate.
                db.delete(dup)  # cascades the dup's candidates / evals / media / child regions
                merged += 1
            db.commit()
        print(f"Done. Merged {merged} duplicate row(s)." if not dry else "Dry run complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
