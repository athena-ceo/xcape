# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Export the per-(country, criterion) AI evaluations to a version-controlled seed file.

Lets the expensive cross-user evaluations be committed to the repo and loaded into any
environment (dev, prod, CI) via `app.db.seed` — no AI cost on prod. Keyed by country
iso/name (not place_id) so it's portable.

Only the SHARED, origin-neutral caches are exported — objective criteria, visa pathways
(`visa_*`) and the cost breakdown (`cost_breakdown`). User-defined / per-community criteria
(`custom_*`) are dev/test artefacts of whoever used the local app, so they're skipped to keep
the committed seed clean (and they regenerate on-demand per user anyway).

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
        skipped_custom = 0
        for e in evals:
            p = places.get(e.place_id)
            if p is None:
                continue
            # Skip user/test-specific custom criteria — keep only the shared caches (objective
            # leaves, visa_* pathways, cost_breakdown) that are safe to ship to every environment.
            if (e.key or "").startswith("custom_"):
                skipped_custom += 1
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
                "meta": e.meta,
                "prompt_fp": e.prompt_fp,
            })
        OUT_FILE.write_text(json.dumps({"evals": out}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Exported {len(out)} shared evaluations to {OUT_FILE.name} "
              f"(skipped {skipped_custom} user/test custom_* rows).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
