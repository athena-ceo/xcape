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

_LEVELS = ["good", "ok", "bad"]


def slugify(label: str) -> str:
    """Stable key for a criterion phrase so the same phrase reuses cached evaluations."""
    slug = re.sub(r"[^a-z0-9]+", "_", str(label).strip().lower()).strip("_")
    return ("custom_" + slug)[:80] or "custom_criterion"


def _eval_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "level": {"type": "string", "enum": _LEVELS},
            "summary_fr": {"type": "string"},
            "summary_en": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["level", "summary_fr", "summary_en", "sources"],
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

    criterion = label + (f" — {description}" if description else "")
    try:
        data = ai_client.respond_json(
            f"For someone relocating to {place.name}, rate how well it satisfies this "
            f"user-defined criterion: \"{criterion}\". Reply with level=good (great fit), "
            f"ok (acceptable) or bad (poor fit), plus a concise 1-2 sentence justification "
            f"in French (summary_fr) and English (summary_en). Use web search for current "
            f"facts. Put sources ONLY in the sources array as bare https URLs.",
            _eval_schema(),
            schema_name="custom_eval",
            web_search=True,
            kind="custom",
            db=db,
            user_id=user_id,
        )
    except ai_client.AIUnavailable:
        return None

    ev = PlaceCustomEval(
        place_id=place.id,
        key=key,
        label=label,
        level=data.get("level", "ok"),
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


def levels_for_place(db: Session, place_id: int, keys: list[str]) -> dict[str, str]:
    """Map of {custom_key: level} for a place, for the given criterion keys."""
    if not keys:
        return {}
    rows = (
        db.query(PlaceCustomEval)
        .filter(PlaceCustomEval.place_id == place_id, PlaceCustomEval.key.in_(keys))
        .all()
    )
    return {r.key: r.level for r in rows}


def reason_for_place(db: Session, place_id: int, key: str, lang: str = "fr") -> dict:
    """Structured justification for a custom-criterion cell (mirrors comparison.criterion_reason)."""
    ev = (
        db.query(PlaceCustomEval)
        .filter(PlaceCustomEval.place_id == place_id, PlaceCustomEval.key == key)
        .first()
    )
    if not ev:
        return {"code": "custom_pending"}
    summary = (ev.summary_fr if lang == "fr" else ev.summary_en) or ev.summary_en or ev.summary_fr
    return {"code": "custom", "text": summary, "sources": ev.sources or []}
