# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""User-defined criteria: let the user invent a criterion and have the AI rate each
country on it. Evaluations are cached per (place, criterion) in place_custom_evals and
shared across users/searches, mirroring the way Place attributes are cached.
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.custom_eval import PlaceCustomEval
from app.models.place import Place
from app.models.search import Search
from app.services import ai_client

# 0-1 fallback values for the colour tier when an old row has no numeric score.
_LEVEL_VALUE = {"good": 1.0, "ok": 0.6, "bad": 0.3}


def slugify(label: str) -> str:
    """Stable key for a criterion phrase so the same phrase reuses cached evaluations."""
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
    *, user_id: int | None = None,
) -> PlaceCustomEval | None:
    """Rate one place on one user-defined criterion (cache-first)."""
    existing = (
        db.query(PlaceCustomEval)
        .filter(PlaceCustomEval.place_id == place.id, PlaceCustomEval.key == key)
        .first()
    )
    if existing:
        return existing

    # The short label is the column name; the (optional) description explains what to judge.
    criterion = label + (f": {description}" if description else "")
    try:
        data = ai_client.respond_json(
            f"For someone relocating to {place.name}, rate how well it satisfies this "
            f"user-defined criterion: \"{criterion}\". Give a score from 0 (poor fit) to "
            f"100 (excellent fit), plus a concise 1-2 sentence justification in French "
            f"(summary_fr) and English (summary_en). Use web search for current facts. "
            f"Put sources ONLY in the sources array as bare https URLs.",
            _eval_schema(),
            schema_name="custom_eval",
            web_search=True,
            kind="custom",
            db=db,
            user_id=user_id,
        )
    except ai_client.AIUnavailable:
        return None

    score = data.get("score")
    ev = PlaceCustomEval(
        place_id=place.id,
        key=key,
        label=label,
        score=score,
        level=level_from_score(score),
        summary_fr=data.get("summary_fr"),
        summary_en=data.get("summary_en"),
        sources=data.get("sources", []),
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def evaluate_for_search(
    db: Session, search: Search, key: str, label: str, description: str | None = None,
    *, user_id: int | None = None,
) -> None:
    """Evaluate every active candidate of a search on a custom criterion (cache-first)."""
    candidates = (
        db.query(Candidate)
        .filter(Candidate.search_id == search.id, Candidate.status == "active")
        .all()
    )
    for cand in candidates:
        if cand.place:
            evaluate(db, cand.place, key, label, description, user_id=user_id)


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
    """Map of {custom_key: level} for a place — used for the cell colour tier."""
    return {k: r.level for k, r in _rows_for_place(db, place_id, keys).items()}


def values_for_place(db: Session, place_id: int, keys: list[str]) -> dict[str, float]:
    """Map of {custom_key: 0-1 value} for a place — used for ranking (score-based)."""
    return {k: value_of(r) for k, r in _rows_for_place(db, place_id, keys).items()}


def reason_for_place(db: Session, place_id: int, key: str, lang: str = "fr") -> dict:
    """Structured justification for a custom-criterion cell (mirrors comparison.criterion_reason).
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
