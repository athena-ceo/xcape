# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Generate the shared, AI-derived per-country data — one command over a generator registry.

Replaces the old per-field scripts (evaluate-all / evaluate-visas / backfill-* / regen-text /
export-evals). Each "generator" knows how to fill ONE kind of data for a place, cache-first; a
single driver loops them, commits per cell (resumable), and handles Ctrl-C. Most of this data
also self-heals lazily when a country is opened — so this is a WARM-UP / finder-prep, not a
requirement (AI calls are expensive and most countries are never visited).

Usage: python -m app.db.generate [--only attributes,criteria,visas,cost] [--force] [--limit N]
                                 [--check] [--export]
  --force   regenerate even fresh cells
  --limit   cap total AI calls this run (resumable; re-run to continue)
  --check   report what's missing/stale, make NO AI calls
  --export  after generating, snapshot the shared caches to the git seed (attributes + evals)
Invoked by `./xcape.sh generate <env> [...]`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.custom_eval import PlaceCustomEval
from app.models.place import Place
from app.services import (
    affordability, ai_client, criteria, criterion_eval, place_research, visa_pathways,
)

_DATA = Path(__file__).resolve().parent.parent / "data"
_EVALS_FILE = _DATA / "criteria_evals_seed.json"
_PLACES_FILE = _DATA / "places_seed.json"


# --- generators: (label, fill, pending) -----------------------------------------------
# fill(db, places, force, budget) -> AI calls made; budget caps calls (None = unlimited).
# pending(db, places) -> count of cells that would be generated (cheap, no AI) — for --check.

def _fill_attributes(db, places, force, budget):
    made = 0
    for p in places:
        if budget is not None and made >= budget:
            break
        made += place_research.fill_missing_attributes(db, p, force=force)
    return made


def _pending_attributes(db, places):
    targets = place_research._all_attrs()
    return sum(1 for p in places if any(k not in (p.attributes or {}) for k in targets))


def _fill_criteria(db, places, force, budget):
    # Cache-first; respect_buckets=False fills bucket-only cells too (a full evaluation).
    return criterion_eval.populate(
        db, places, criteria.objective_keys(), force=force, respect_buckets=False, limit=budget)


def _pending_criteria(db, places):
    keys = criteria.objective_keys()
    have = db.query(PlaceCustomEval).filter(PlaceCustomEval.key.in_(keys)).count()
    return max(0, len(places) * len(keys) - have)


def _fill_cells(db, places, force, budget, keys, evaluate):
    """Shared loop for the per-(place, key) cache caches (visas, cost): call `evaluate`, counting
    a cell only when its fingerprint actually changed (a real generation)."""
    made = 0
    for p in places:
        for key in keys:
            if budget is not None and made >= budget:
                return made
            before = (
                db.query(PlaceCustomEval)
                .filter(PlaceCustomEval.place_id == p.id, PlaceCustomEval.key == key).first()
            )
            bfp = before.prompt_fp if before is not None else None
            try:
                ev = evaluate(db, p, key, force)
            except ai_client.AIUnavailable:
                raise
            except Exception as e:  # never let one cell kill a long unattended run
                db.rollback()
                print(f"  skip {p.name}/{key}: {type(e).__name__}: {e}")
                continue
            if ev is not None and ev.prompt_fp != bfp:
                made += 1
    return made


def _fill_visas(db, places, force, budget):
    keys = [f"visa_{c}" for c in visa_pathways.FINDER_CATEGORIES]
    return _fill_cells(
        db, places, force, budget, keys,
        lambda db, p, key, force: visa_pathways.evaluate_pathway(
            db, p, key.removeprefix("visa_"), force=force))


def _fill_cost(db, places, force, budget):
    return _fill_cells(
        db, places, force, budget, [affordability.BREAKDOWN_KEY],
        lambda db, p, key, force: affordability.evaluate_breakdown(db, p, force=force))


def _pending_keys(db, places, keys):
    have = db.query(PlaceCustomEval).filter(PlaceCustomEval.key.in_(keys)).count()
    return max(0, len(places) * len(keys) - have)


GENERATORS: dict[str, tuple] = {
    "attributes": ("country attributes (english, tax basis, social…)", _fill_attributes,
                   _pending_attributes),
    "criteria": ("objective criterion evaluations", _fill_criteria, _pending_criteria),
    "visas": ("golden-visa finder pathways", _fill_visas,
              lambda db, ps: _pending_keys(db, ps, [f"visa_{c}" for c in visa_pathways.FINDER_CATEGORIES])),
    "cost": ("budget cost breakdowns", _fill_cost,
             lambda db, ps: _pending_keys(db, ps, [affordability.BREAKDOWN_KEY])),
}


# --- export to the git seed -----------------------------------------------------------
def _export(db: Session) -> None:
    """Snapshot the SHARED caches to the committed seed so other environments load them for
    free (no AI): criterion evals → criteria_evals_seed.json (skipping user/test custom_* rows),
    and place attributes → places_seed.json (refreshed in place by ISO, structure preserved)."""
    places = {p.id: p for p in db.query(Place).all()}
    evals, skipped = [], 0
    for e in db.query(PlaceCustomEval).all():
        p = places.get(e.place_id)
        if p is None:
            continue
        if (e.key or "").startswith("custom_"):  # per-user/test data — not shared, don't ship
            skipped += 1
            continue
        evals.append({
            "country": p.name, "iso": p.iso_code, "key": e.key, "label": e.label,
            "score": e.score, "level": e.level, "summary_fr": e.summary_fr,
            "summary_en": e.summary_en, "sources": e.sources or [], "meta": e.meta,
            "prompt_fp": e.prompt_fp,
        })
    _EVALS_FILE.write_text(json.dumps({"evals": evals}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  evals → {_EVALS_FILE.name}: {len(evals)} ({skipped} user/test custom_* skipped)")

    by_iso = {}
    by_name = {}
    for p in db.query(Place).filter(Place.kind == "country").all():
        if p.iso_code:
            by_iso[p.iso_code.upper()] = p
        by_name[p.name] = p
    seed = json.loads(_PLACES_FILE.read_text(encoding="utf-8"))
    refreshed = 0
    for c in seed.get("countries", []):
        p = by_iso.get((c.get("iso_code") or "").upper()) or by_name.get(c.get("name"))
        if p is None:
            continue
        c["attributes"] = p.attributes or {}
        if p.summary_fr:
            c["summary_fr"] = p.summary_fr
        if p.summary_en:
            c["summary_en"] = p.summary_en
        refreshed += 1
    _PLACES_FILE.write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  attributes → {_PLACES_FILE.name}: refreshed {refreshed} countries")


def _arg_value(args: list[str], flag: str) -> str | None:
    return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else None


def main() -> None:
    args = sys.argv[1:]
    force = "--force" in args
    check = "--check" in args
    export = "--export" in args
    only = (_arg_value(args, "--only") or "").split(",") if "--only" in args else None
    limit = int(_arg_value(args, "--limit")) if "--limit" in args else None
    selected = [k for k in GENERATORS if only is None or k in only]
    if not selected:
        print(f"Unknown --only group. Choose from: {', '.join(GENERATORS)}")
        return

    db = SessionLocal()
    try:
        places = db.query(Place).filter(Place.kind == "country", Place.active.is_(True)).all()
        if check:
            print(f"Pending AI work across {len(places)} countries (no calls made):")
            for k in selected:
                label, _, pending = GENERATORS[k]
                print(f"  {k:<11}{pending(db, places):>6}  {label}")
            return

        print(f"Generating [{', '.join(selected)}] across {len(places)} countries "
              f"(force={force}). Cache-first, resumable, Ctrl-C-safe.")
        budget = limit
        total = 0
        for k in selected:
            label, fill, _ = GENERATORS[k]
            try:
                made = fill(db, places, force, budget)
            except ai_client.AIUnavailable:
                print("AI unavailable (no API key) — stopping (re-run to resume).")
                break
            total += made
            print(f"  {k}: {made} generated")
            if budget is not None:
                budget = max(0, budget - made)
                if budget == 0:
                    print(f"Hit --limit ({limit}).")
                    break
        print(f"Done. {total} generated this run.")
        if export:
            print("Exporting shared caches to the git seed…")
            _export(db)
    except KeyboardInterrupt:
        print("\nInterrupted — progress saved (resumable). Re-run to continue.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
