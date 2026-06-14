# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Unified per-(country, criterion) AI evaluation cache.

Every criterion the app scores objectively — built-in (safety, taxation, healthcare…) and
user-defined (custom_*) — is rated 0-100 by the AI with a bilingual justification and
sources, cached in `place_custom_evals` and shared across all users/searches (like the
Place data). This is what lets us populate the ~190 countries that have no seed values, and
what the comparison pop-up shows instantly. Cache-first; refreshable by staleness or admin.

(The table is still named `place_custom_evals` for historical reasons; it now holds every
criterion's evaluation, not just custom ones.)
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.custom_eval import PlaceCustomEval
from app.models.place import Place
from app.services import ai_client, criteria

# 0-1 fallback values for the colour tier when an old row has no numeric score.
_LEVEL_VALUE = {"good": 1.0, "ok": 0.6, "bad": 0.3}
STALE_DAYS = 30  # evals older than this are refreshed by populate(stale_days=...)


def slugify(label: str) -> str:
    """Stable key for a custom criterion phrase so it reuses cached evaluations."""
    slug = re.sub(r"[^a-z0-9]+", "_", str(label).strip().lower()).strip("_")
    return ("custom_" + slug)[:80] or "custom_criterion"


def level_from_score(score: int | None) -> str:
    """Colour tier from a 0-100 score, matching shortlist.quality_tier thresholds."""
    if score is None:
        return "ok"
    return "good" if score >= 70 else ("ok" if score >= 45 else "bad")


def value_of(ev: PlaceCustomEval) -> float:
    """0-1 scoring value: the numeric score when present, else the level fallback."""
    if ev.score is not None:
        return max(0.0, min(1.0, ev.score / 100))
    return _LEVEL_VALUE.get(ev.level, 0.5)


def _is_stale(ev: PlaceCustomEval, stale_days: int) -> bool:
    if not stale_days or ev.freshness_at is None:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
    ts = ev.freshness_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts < cutoff


def _eval_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "summary_fr": {"type": "string"},
            "summary_en": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["score", "summary_fr", "summary_en", "sources"],
        "additionalProperties": False,
    }


def evaluate(
    db: Session, place: Place, key: str, label: str, description: str | None = None,
    *, user_id: int | None = None, force: bool = False, stale_days: int = 0,
) -> PlaceCustomEval | None:
    """Rate one place on one criterion (cache-first). Re-evaluates if `force` or the cached
    row is older than `stale_days`. Returns the (possibly cached) eval, or None if AI is off."""
    existing = (
        db.query(PlaceCustomEval)
        .filter(PlaceCustomEval.place_id == place.id, PlaceCustomEval.key == key)
        .first()
    )
    if existing and not force and not _is_stale(existing, stale_days):
        return existing

    # The short label is the column name; the (optional) description explains what to judge.
    criterion = label + (f": {description}" if description else "")
    try:
        data = ai_client.respond_json(
            f"For someone relocating to {place.name}, rate how well it satisfies this "
            f"criterion: \"{criterion}\". Give a score from 0 (poor) to 100 (excellent) "
            f"from the resident's point of view, plus a concise 1-2 sentence justification "
            f"in French (summary_fr) and English (summary_en). Use web search for current "
            f"facts. Put sources ONLY in the sources array as bare https URLs.",
            _eval_schema(),
            schema_name="criterion_eval",
            web_search=True,
            model=settings.openai_chat_model,  # lightweight scoring → use the faster model
            kind="custom",
            db=db,
            user_id=user_id,
        )
    except ai_client.AIUnavailable:
        return None

    score = data.get("score")
    if existing:  # refresh in place
        existing.score = score
        existing.level = level_from_score(score)
        existing.label = label
        existing.summary_fr = data.get("summary_fr")
        existing.summary_en = data.get("summary_en")
        existing.sources = data.get("sources", [])
        existing.freshness_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing

    ev = PlaceCustomEval(
        place_id=place.id, key=key, label=label, score=score,
        level=level_from_score(score),
        summary_fr=data.get("summary_fr"), summary_en=data.get("summary_en"),
        sources=data.get("sources", []),
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def populate(db: Session, places: list[Place], keys: list[str], *,
             stale_days: int = 0, force: bool = False, limit: int | None = None,
             respect_buckets: bool = True) -> int:
    """Progressively evaluate (place × key) cells, cache-first. Returns how many AI calls
    were made. Resumable: re-run to continue. `limit` caps the AI calls this run.
    With `respect_buckets`, an objective leaf that already has a seed bucket value is left
    alone (no AI call) unless `force` — this bounds cost to the genuinely-missing cells."""
    defs = criteria.definitions()  # objective built-ins, resolved the same way as everywhere
    made = 0
    for place in places:
        attrs = place.attributes or {}
        for key in keys:
            if limit is not None and made >= limit:
                return made
            d = defs.get(key)
            if d is None:
                continue  # not an AI-evaluable criterion
            if respect_buckets and not force and attrs.get(key):
                continue
            before = (
                db.query(PlaceCustomEval)
                .filter(PlaceCustomEval.place_id == place.id, PlaceCustomEval.key == key)
                .first()
            )
            if before and not force and not _is_stale(before, stale_days):
                continue
            ev = evaluate(db, place, key, d["label"], d.get("description"),
                          force=force, stale_days=stale_days)
            if ev is None:
                continue
            made += 1
    return made


def _rows_for_place(db: Session, place_id: int, keys: list[str]) -> dict[str, PlaceCustomEval]:
    if not keys:
        return {}
    rows = (
        db.query(PlaceCustomEval)
        .filter(PlaceCustomEval.place_id == place_id, PlaceCustomEval.key.in_(keys))
        .all()
    )
    return {r.key: r for r in rows}


def levels_for_place(db: Session, place_id: int, keys: list[str]) -> dict[str, str]:
    """Map of {key: level} for a place — used for the cell colour tier."""
    return {k: r.level for k, r in _rows_for_place(db, place_id, keys).items()}


def values_for_place(db: Session, place_id: int, keys: list[str]) -> dict[str, float]:
    """Map of {key: 0-1 value} for a place — used for ranking (score-based)."""
    return {k: value_of(r) for k, r in _rows_for_place(db, place_id, keys).items()}


def values_for_places(db: Session, place_ids: list[int], keys: list[str]) -> dict[int, dict[str, float]]:
    """Batch {place_id: {key: 0-1 value}} for scoring a whole pool in one query."""
    if not place_ids or not keys:
        return {}
    rows = (
        db.query(PlaceCustomEval)
        .filter(PlaceCustomEval.place_id.in_(place_ids), PlaceCustomEval.key.in_(keys))
        .all()
    )
    out: dict[int, dict[str, float]] = {}
    for r in rows:
        out.setdefault(r.place_id, {})[r.key] = value_of(r)
    return out


def evals_for_place(db: Session, place_id: int, keys: list[str]) -> dict[str, PlaceCustomEval]:
    """All cached eval rows for a place keyed by criterion key (one query)."""
    return _rows_for_place(db, place_id, keys)


def reason_from_eval(ev: PlaceCustomEval, lang: str = "fr") -> dict:
    """Pop-up justification (score + text + sources) from an already-loaded eval row."""
    summary = (ev.summary_fr if lang == "fr" else ev.summary_en) or ev.summary_en or ev.summary_fr
    return {"code": "custom", "text": summary, "score": ev.score, "sources": ev.sources or []}


def reason_for_place(db: Session, place_id: int, key: str, lang: str = "fr") -> dict:
    """Structured justification for a criterion cell (mirrors comparison.criterion_reason).
    Carries the AI score + justification shown in the explanation pop-up."""
    ev = (
        db.query(PlaceCustomEval)
        .filter(PlaceCustomEval.place_id == place_id, PlaceCustomEval.key == key)
        .first()
    )
    if not ev:
        return {"code": "custom_pending"}
    summary = (ev.summary_fr if lang == "fr" else ev.summary_en) or ev.summary_en or ev.summary_fr
    return {"code": "custom", "text": summary, "score": ev.score, "sources": ev.sources or []}
