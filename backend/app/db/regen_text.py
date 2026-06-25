# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Regenerate cached AI *text* whose language/shape changed, and backfill localized labels.

Some cached drill-down text was previously generated in a single language and is now
bilingual (trend-lens `metric`, visa requirement bullets); their prompt versions were bumped,
so the affected rows are version-stale. The normal drill-down "fill" loop treats any existing
row as done, so stale rows never self-heal there — this command regenerates them.

It also backfills `label_fr` / `label_en` onto custom criteria created before labels were
localized, so the comparison table / drill-down show a translated column header (not the raw
text the user typed) in either UI language.

Cache-first and resumable: re-run to continue; pass --force to regenerate text even when it
looks current. --no-text / --no-labels skip a phase.

Usage: python -m app.db.regen_text [--force] [--no-text] [--no-labels]
Invoked by `./xcape.sh regen-text <env>`.
"""

from __future__ import annotations

import sys

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.db.session import SessionLocal
from app.models.custom_eval import PlaceCustomEval
from app.models.place import Place
from app.models.profile import Profile
from app.models.search import Search
from app.services import ai_client, criteria, criterion_eval, custom_criteria, visa_pathways

_COMMUNITY_LIKE = f"{criterion_eval._COMMUNITY_SAFETY_PREFIX}%"


def _custom_defs_map(db: Session) -> dict[str, dict]:
    """{key: {label, description}} gathered from every search + profile, so a stale custom
    eval can be regenerated with the same label/description it was created from (a matching
    fingerprint, so it doesn't re-stale next run)."""
    out: dict[str, dict] = {}
    for s in db.query(Search).all():
        for c in (s.custom_criteria or []):
            if c.get("key"):
                out.setdefault(c["key"], {"label": c.get("label"), "description": c.get("description")})
    for p in db.query(Profile).all():
        for c in (p.custom_criteria or []):
            if c.get("key"):
                out.setdefault(c["key"], {"label": c.get("label"), "description": c.get("description")})
    return out


def _regen_trend_objective(db: Session, places: list[Place], force: bool) -> int:
    """Regenerate the built-in trend-lens criteria (safety, political_stability) — only EXISTING
    rows, cache-first, so the run just refreshes the version-stale text (it does not gap-fill
    countries that were never evaluated — that's `evaluate-all`'s job)."""
    keys = [k for k in criteria.objective_keys() if criterion_eval.lens_for(k) == "trend"]
    if not keys:
        return 0
    defs = criteria.definitions()
    made = 0
    for place in places:
        rows = criterion_eval.evals_for_place(db, place.id, keys)  # existing rows only
        for key, r in rows.items():
            d = defs.get(key) or {"label": r.label or key, "description": None}
            before = r.prompt_fp
            try:
                res = criterion_eval.evaluate(
                    db, place, key, d["label"], d.get("description"), force=force)
            except Exception as e:
                db.rollback()
                print(f"  skip {place.name}/{key}: {type(e).__name__}: {e}")
                continue
            if res is not None and res.prompt_fp != before:
                made += 1
    return made


def _regen_custom_trend(db: Session, places: list[Place], force: bool) -> int:
    """Regenerate per-community safety criteria (custom trend-lens rows) — these aren't covered
    by populate() (not objective built-ins), so do them explicitly, cache-first."""
    defs = _custom_defs_map(db)
    made = 0
    for place in places:
        rows = (
            db.query(PlaceCustomEval)
            .filter(PlaceCustomEval.place_id == place.id,
                    PlaceCustomEval.key.like(_COMMUNITY_LIKE))
            .all()
        )
        for r in rows:
            d = defs.get(r.key, {"label": r.label, "description": None})
            before = r.prompt_fp
            try:
                res = criterion_eval.evaluate(
                    db, place, r.key, d.get("label") or r.label, d.get("description"),
                    lens="trend", force=force)
            except Exception as e:  # never let one cell kill the run
                db.rollback()
                print(f"  skip {place.name}/{r.key}: {type(e).__name__}: {e}")
                continue
            if res is not None and res.prompt_fp != before:
                made += 1
    return made


def _regen_visa(db: Session, places: list[Place], force: bool) -> int:
    """Regenerate cached visa-pathway rows (the requirement bullets are now bilingual) —
    cache-first, so only version-stale rows call the AI."""
    made = 0
    for place in places:
        rows = visa_pathways.cached_rows(db, place.id)  # {category: row}
        for cat, ev in rows.items():
            before = ev.prompt_fp
            try:
                res = visa_pathways.evaluate_pathway(db, place, cat, force=force)
            except Exception as e:
                db.rollback()
                print(f"  skip {place.name}/visa_{cat}: {type(e).__name__}: {e}")
                continue
            if res is not None and res.prompt_fp != before:
                made += 1
    return made


def _backfill_labels(db: Session) -> int:
    """Add label_fr/label_en to custom criteria that lack them (created before labels were
    localized). Translations are memoized per (label, description) so identical criteria across
    searches/profiles cost one call."""
    memo: dict[tuple, dict] = {}

    def localized(label: str, description: str | None) -> dict:
        key = (label or "", description or "")
        if key not in memo:
            memo[key] = custom_criteria.localize_label(db, label, description)
        return memo[key]

    updated = 0

    def heal(rows, attr: str) -> int:
        n = 0
        for row in rows:
            defs = [dict(c) for c in (getattr(row, attr) or [])]
            changed = False
            for c in defs:
                if not c.get("key") or (c.get("label_fr") and c.get("label_en")):
                    continue
                c.update(localized(c.get("label") or c["key"], c.get("description")))
                changed = True
                n += 1
            if changed:
                setattr(row, attr, defs)
                flag_modified(row, attr)
                db.commit()
        return n

    updated += heal(db.query(Search).all(), "custom_criteria")
    updated += heal(db.query(Profile).all(), "custom_criteria")
    return updated


def main() -> None:
    force = "--force" in sys.argv
    do_text = "--no-text" not in sys.argv
    do_labels = "--no-labels" not in sys.argv

    db = SessionLocal()
    try:
        places = db.query(Place).filter(Place.kind == "country").all()
        if do_text:
            print(f"Regenerating stale drill-down text across {len(places)} countries "
                  f"(force={force}). Cache-first, resumable.")
            try:
                t = _regen_trend_objective(db, places, force)
                c = _regen_custom_trend(db, places, force)
                v = _regen_visa(db, places, force)
                print(f"  trend criteria: {t} · community safety: {c} · visa pathways: {v}")
            except ai_client.AIUnavailable:
                print("  AI unavailable (no API key) — skipping text regeneration.")
        if do_labels:
            print("Backfilling custom-criterion labels (label_fr / label_en)…")
            try:
                n = _backfill_labels(db)
                print(f"  localized {n} custom criteria.")
            except ai_client.AIUnavailable:
                print("  AI unavailable (no API key) — skipping label backfill.")
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
