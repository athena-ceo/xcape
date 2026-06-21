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


def _upsert(db: Session, *, kind: str, name: str, overwrite: bool = True, **fields) -> Place:
    place = db.query(Place).filter(Place.kind == kind, Place.name == name).first()
    if place is not None and not overwrite:
        return place  # insert-only mode: leave existing rows untouched
    if place is None:
        place = Place(kind=kind, name=name)
        db.add(place)
    for key, value in fields.items():
        setattr(place, key, value)
    db.flush()
    return place


def seed_criteria(db: Session) -> bool:
    """Seed the editable criteria registry into app_config from the bundled file, once.
    Idempotent: leaves an existing (possibly admin-edited) registry untouched."""
    from app.models.app_config import AppConfig
    from app.services import criteria

    if db.get(AppConfig, "criteria") is not None:
        return False
    db.add(AppConfig(key="criteria", value=criteria.file_registry()))
    db.commit()
    criteria.invalidate()
    return True


_EVALS_FILE = Path(__file__).resolve().parent.parent / "data" / "criteria_evals_seed.json"


def seed_evals(db: Session, overwrite: bool = False) -> int:
    """Load committed per-(country, criterion) AI evaluations into place_custom_evals so a
    fresh DB gets them without paying for AI. Insert-only by default (existing rows are left
    as-is) — deploy bootstraps + fills gaps but never clobbers prod data. Pass overwrite=True
    (via `reseed-data`) to force the committed values onto existing rows. Only touches keys
    present in the seed file, so user-defined custom-criterion evals are never affected."""
    from app.models.custom_eval import PlaceCustomEval

    if not _EVALS_FILE.exists():
        return 0
    rows = json.loads(_EVALS_FILE.read_text(encoding="utf-8")).get("evals", [])
    n = 0
    for r in rows:
        place = None
        if r.get("iso"):
            place = db.query(Place).filter(Place.iso_code == r["iso"]).first()
        if place is None:
            place = db.query(Place).filter(Place.name == r.get("country")).first()
        if place is None:
            continue
        ev = (db.query(PlaceCustomEval)
              .filter(PlaceCustomEval.place_id == place.id, PlaceCustomEval.key == r["key"]).first())
        if ev is not None and not overwrite:
            continue  # insert-only: keep the existing eval
        if ev is None:
            ev = PlaceCustomEval(place_id=place.id, key=r["key"])
            db.add(ev)
        ev.label = r.get("label") or r["key"]
        ev.prompt_fp = r.get("prompt_fp")  # carry the prompt version so it isn't re-evaluated
        ev.score = r.get("score")
        ev.level = r.get("level") or "ok"
        ev.summary_fr = r.get("summary_fr")
        ev.summary_en = r.get("summary_en")
        ev.sources = r.get("sources") or []
        n += 1
    db.commit()
    return n


def seed(db: Session, overwrite: bool = False) -> int:
    """Bootstrap the place database from the bundled files. Insert-only by default (deploy
    fills gaps / adds new countries but never overwrites existing rows); overwrite=True
    (via `reseed-data`) force-refreshes places + evals from the committed snapshot."""
    seed_criteria(db)
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    count = 0
    for country in data.get("countries", []):
        c = _upsert(
            db,
            kind="country",
            name=country["name"],
            overwrite=overwrite,
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
                overwrite=overwrite,
                parent_id=c.id,
                attributes=region.get("attributes", {}),
                source="seed",
            )
            count += 1
    db.commit()
    evals = seed_evals(db, overwrite=overwrite)  # load committed AI evaluations, if any
    if evals:
        print(f"{'Refreshed' if overwrite else 'Loaded'} {evals} cached criterion evaluations.")
    return count


def main() -> None:
    db = SessionLocal()
    try:
        n = seed(db)  # insert-only bootstrap
        print(f"Seeded {n} places (insert-only; existing rows kept).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
