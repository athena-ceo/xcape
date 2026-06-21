# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Export the per-(country, criterion) AI evaluations to a version-controlled seed file.

Lets the expensive cross-user evaluations be committed to the repo and loaded into any
environment (dev, prod, CI) via `app.db.seed` — no AI cost on prod. Keyed by country
iso/name (not place_id) so it's portable.

Usage: python -m app.db.export_evals     →  app/data/criteria_evals_seed.json
"""

from __future__ import annotations

import json
from pathlib import Path

from app.db.session import SessionLocal
from app.models.custom_eval import PlaceCustomEval
from app.models.place import Place

OUT_FILE = Path(__file__).resolve().parent.parent / "data" / "criteria_evals_seed.json"


def main() -> None:
    db = SessionLocal()
    try:
        places = {p.id: p for p in db.query(Place).all()}
        evals = db.query(PlaceCustomEval).all()
        out = []
        for e in evals:
            p = places.get(e.place_id)
            if p is None:
                continue
            out.append({
                "country": p.name,
                "iso": p.iso_code,
                "key": e.key,
                "label": e.label,
                "score": e.score,
                "level": e.level,
                "summary_fr": e.summary_fr,
                "summary_en": e.summary_en,
                "sources": e.sources or [],
                "prompt_fp": e.prompt_fp,
            })
        OUT_FILE.write_text(json.dumps({"evals": out}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Exported {len(out)} evaluations to {OUT_FILE.name}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
