# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Read-only check: does the live place_custom_evals data match the committed, recalibrated
`criteria_evals_seed.json`?

Because deploy seeding is INSERT-ONLY (it never overwrites existing rows), an environment that
was seeded before the recalibration was committed will still hold the old eval scores. This
compares every numeric-scored seed row against the DB and reports match / differ / missing, so
you can tell whether `reseed-data` is needed. Run via `./xcape.sh verify-evals <dev|prod>`.
"""

from __future__ import annotations

import json

from app.db.seed import _EVALS_FILE
from app.db.session import SessionLocal
from app.models.custom_eval import PlaceCustomEval
from app.models.place import Place


def main() -> None:
    db = SessionLocal()
    try:
        rows = json.loads(_EVALS_FILE.read_text(encoding="utf-8")).get("evals", [])
        checked = match = differ = missing = no_place = 0
        sample: list[tuple] = []
        for r in rows:
            if r.get("score") is None:  # level-only rows: nothing numeric to compare
                continue
            place = None
            if r.get("iso"):
                place = db.query(Place).filter(Place.iso_code == r["iso"]).first()
            if place is None:
                place = db.query(Place).filter(Place.name == r.get("country")).first()
            if place is None:
                no_place += 1
                continue
            checked += 1
            ev = (db.query(PlaceCustomEval)
                  .filter(PlaceCustomEval.place_id == place.id, PlaceCustomEval.key == r["key"])
                  .first())
            if ev is None or ev.score is None:
                missing += 1
            elif int(ev.score) == int(r["score"]):
                match += 1
            else:
                differ += 1
                if len(sample) < 12:
                    sample.append((r.get("country"), r["key"], r["score"], ev.score))

        print(f"Committed seed: {_EVALS_FILE.name}")
        print(f"Numeric eval rows checked: {checked}")
        print(f"  match:   {match}")
        print(f"  differ:  {differ}")
        print(f"  missing: {missing}")
        if no_place:
            print(f"  (seed rows whose country isn't in this DB: {no_place})")
        if sample:
            print("\nSample differences (country, criterion, seed_score, db_score):")
            for c, k, seed_s, db_s in sample:
                print(f"  {c:24s} {k:22s} seed={seed_s:<4} db={db_s}")
        if differ or missing:
            print("\n=> DB does NOT match the committed recalibration.")
            print("   Run `./xcape.sh reseed-data <env>` to apply it.")
        else:
            print("\n=> DB matches the committed recalibrated seed. Up to date.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
