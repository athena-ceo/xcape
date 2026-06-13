# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Load the bundled place database (countries + regions) into Postgres.

Idempotent: existing places (matched by kind+name) are updated, not duplicated.
Run via `./xcape.sh seed dev` or `python -m app.db.seed`.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.place import Place

SEED_FILE = Path(__file__).resolve().parent.parent / "data" / "places_seed.json"


def _upsert(db: Session, *, kind: str, name: str, **fields) -> Place:
    place = db.query(Place).filter(Place.kind == kind, Place.name == name).first()
    if place is None:
        place = Place(kind=kind, name=name)
        db.add(place)
    for key, value in fields.items():
        setattr(place, key, value)
    db.flush()
    return place


def seed(db: Session) -> int:
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    count = 0
    for country in data.get("countries", []):
        c = _upsert(
            db,
            kind="country",
            name=country["name"],
            iso_code=country.get("iso_code"),
            attributes=country.get("attributes", {}),
            summary_fr=country.get("summary_fr"),
            summary_en=country.get("summary_en"),
            source="seed",
        )
        count += 1
        for region in country.get("regions", []):
            _upsert(
                db,
                kind="region",
                name=region["name"],
                parent_id=c.id,
                attributes=region.get("attributes", {}),
                source="seed",
            )
            count += 1
    db.commit()
    return count


def main() -> None:
    db = SessionLocal()
    try:
        n = seed(db)
        print(f"Seeded/updated {n} places.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
