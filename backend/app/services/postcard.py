# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

""""Postcard from your future" + pre-mortem for one country (the red and black hats of the
emotional roadmap). The postcard imagines an ordinary day there for THIS household; the
pre-mortem names, candidly, why they might be unhappy two years in. Both are grounded in the
user's profile and story and in the country's own per-criterion texts — and are always
presented as imagined, never as fact. One AI call per user × country × language, cached and
re-written when the inputs change (fingerprint).
"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.emotion import Postcard
from app.models.place import Place
from app.models.search import Search
from app.models.user import User
from app.services import ai_client, board, criteria
from app.services import shortlist as sl

_TOP_CRITERIA = 8  # the user's heaviest-weighted criteria give the pre-mortem its substance


def _inputs(db: Session, user: User, place: Place, search: Search | None, lang: str) -> dict:
    p = user.profile
    story = (getattr(p, "story", None) or {}) if p else {}
    weights = sl._effective_weights(p)
    custom = (search.custom_criteria or []) if search else []
    for c in custom:
        if c.get("key"):
            weights[c["key"]] = float(c.get("weight", 1.0))
    top = [k for k, w in sorted(weights.items(), key=lambda kv: -kv[1]) if w > 0][:_TOP_CRITERIA]
    details = {r["key"]: r for r in board.criterion_details(db, place, p, custom, lang)}
    facts = []
    for k in top:
        r = details.get(k)
        if r and (r.get("summary") or r.get("score") is not None):
            facts.append({"criterion": r.get("label") or criteria.label(k, lang),
                          "score": r.get("score"), "summary": (r.get("summary") or "")[:300]})
    persona = criteria.persona(getattr(p, "persona", None)) if p else None
    return {
        "country": place.name,
        "household": getattr(p, "household_type", None),
        "children_planned": getattr(p, "intends_children", None),
        "profile": (persona or {}).get("label_en"),
        "lives_in": user.current_country,
        "family_in": user.family_countries or [],
        "climate_wanted": getattr(p, "climate_pref", None),
        "speaks": ((getattr(p, "language_skills", None) or {}).get("known") or []) if p else [],
        "hopes": story.get("hopes") or [],
        "worries": story.get("worries") or [],
        "their_words": ((getattr(p, "priorities_text", None) or "")[:800]) if p else "",
        "criteria": facts,
    }


def fingerprint(inputs: dict) -> str:
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "setting": {"type": "string"},
            "postcard": {"type": "string"},
            "premortem": {
                "type": "array", "minItems": 3, "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {"title": {"type": "string"}, "text": {"type": "string"}},
                    "required": ["title", "text"], "additionalProperties": False,
                },
            },
        },
        "required": ["setting", "postcard", "premortem"],
        "additionalProperties": False,
    }


def _payload(row: Postcard, stale: bool = False) -> dict:
    return {"pending": False, "stale": stale, "setting": row.setting, "postcard": row.postcard,
            "premortem": row.premortem or [], "created_at": row.created_at}


def get(db: Session, user: User, place: Place, search: Search | None, lang: str) -> dict:
    """The cached postcard, `pending` when none exists for these inputs (no AI call)."""
    if sl.is_home(db, user, place):
        return {"home": True, "pending": False}
    row = db.query(Postcard).filter_by(user_id=user.id, place_id=place.id, lang=lang).first()
    if row is None:
        return {"pending": True}
    if row.fingerprint != fingerprint(_inputs(db, user, place, search, lang)):
        return {**_payload(row, stale=True), "pending": True}  # show the old one while re-writing
    return _payload(row)


def generate(db: Session, user: User, place: Place, search: Search | None, lang: str,
             force: bool = False) -> dict:
    """Write (or re-write) the postcard + pre-mortem. Cache-first unless `force`."""
    if sl.is_home(db, user, place):
        return {"home": True, "pending": False}
    lang = "fr" if lang == "fr" else "en"
    inputs = _inputs(db, user, place, search, lang)
    fp = fingerprint(inputs)
    row = db.query(Postcard).filter_by(user_id=user.id, place_id=place.id, lang=lang).first()
    if row is not None and row.fingerprint == fp and not force:
        return _payload(row)
    language = "French (vous)" if lang == "fr" else "English"
    try:
        data = ai_client.respond_json(
            f"Write for someone considering a move to {place.name}. Everything we know about them "
            f"and about {place.name} (scores 0-100 and summaries from our research):\n"
            f"{json.dumps(inputs, ensure_ascii=False, indent=1)}\n\n"
            f"In {language}:\n"
            "- setting: ONE real town or city in the country that fits this household "
            "(climate, size, language, budget) — just its name.\n"
            "- postcard: 110-150 words, second person, present tense: an ordinary, specific day "
            "in their new life in that place — morning to evening, sensory details, the people "
            "around them (their household as described). Let 1-2 of their hopes come true where "
            "the research supports it. No prices, statistics or facts beyond the research given; "
            "no clichés; warm but not saccharine.\n"
            "- premortem: exactly 3 items. Imagine it is two years later and they are unhappy "
            "there. Each item: a short title (≤ 8 words) and ≤ 45 words on why — grounded in the "
            "weaker scores, the research summaries and their own worries. Candid, specific, "
            "not alarmist; one item may be about what they would miss from home.",
            _schema(),
            schema_name="postcard",
            model=settings.openai_chat_model,
            kind="postcard",
            db=db,
            user_id=user.id,
        )
    except ai_client.AIUnavailable:
        return {"pending": False, "unavailable": True}
    premortem = [{"title": (i.get("title") or "").strip(), "text": (i.get("text") or "").strip()}
                 for i in (data.get("premortem") or [])][:3]
    if row is None:
        row = Postcard(user_id=user.id, place_id=place.id, lang=lang)
        db.add(row)
    row.fingerprint, row.setting = fp, (data.get("setting") or "").strip()[:120] or None
    row.postcard, row.premortem = (data.get("postcard") or "").strip(), premortem
    try:
        db.commit()
    except IntegrityError:
        # Opened twice at once: the other request wrote it first — show theirs.
        db.rollback()
        row = db.query(Postcard).filter_by(user_id=user.id, place_id=place.id, lang=lang).first()
        if row is None:
            raise
        return _payload(row)
    db.refresh(row)
    return _payload(row)
