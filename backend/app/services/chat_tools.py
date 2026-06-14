# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Tools the chat assistant can call to act on the user's search (function calling).

Each tool maps to existing services so the chat stays consistent with the rest of the
app. `execute` runs a tool against the current search and returns (result, changed),
where `changed` tells the frontend to re-read the board.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.place import Place
from app.models.profile import Profile
from app.models.search import Search
from app.models.user import User
from app.services import ai_client, place_research
from app.services import shortlist as sl

_CRITERIA = ", ".join(sl.CRITERIA_KEYS)

TOOLS = [
    {
        "type": "function",
        "name": "set_importance",
        "description": (
            "Set how much one or more criteria matter, as weights 0 (ignore) to 3 "
            f"(critical). Valid keys: {_CRITERIA}. Re-ranks the candidates."
        ),
        "parameters": {
            "type": "object",
            "properties": {"weights": {"type": "object", "additionalProperties": {"type": "number"}}},
            "required": ["weights"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "set_filter",
        "description": (
            "Apply or clear hard filters that exclude countries. language_ease=true keeps "
            "only countries where the user can communicate; climate keeps only a given "
            "climate (cold/temperate/mild/warm/tropical); visa=true keeps only easy-to-"
            "settle countries. Pass false/null to clear a filter. Rebuilds the shortlist."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "language_ease": {"type": ["boolean", "null"]},
                "climate": {"type": ["string", "null"]},
                "visa": {"type": ["boolean", "null"]},
            },
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "add_country",
        "description": "Add a country to the comparison board. Use the English country name.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "select_country",
        "description": "Select or unselect a country for the comparison board (max 5 selected). English name.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "selected": {"type": "boolean"}},
            "required": ["name", "selected"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "rebuild_shortlist",
        "description": "Rebuild the shortlist from the current profile (re-pick the best matches).",
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
]


def _profile(db: Session, user: User) -> Profile:
    if user.profile is None:
        p = Profile(user_id=user.id)
        db.add(p)
        db.commit()
        db.refresh(p)
        return p
    return user.profile


def _find_place(db: Session, name: str) -> Place | None:
    return db.query(Place).filter(Place.kind == "country", Place.name.ilike(name)).first()


def _selected_count(db: Session, search_id: int) -> int:
    return (
        db.query(Candidate)
        .filter(Candidate.search_id == search_id, Candidate.status == "active",
                Candidate.selected.is_(True))
        .count()
    )


def execute(db: Session, user: User, search: Search, name: str, args: dict) -> tuple[dict, bool]:
    if name == "set_importance":
        p = _profile(db, user)
        weights = dict(p.criteria_weights or {})
        for k, v in (args.get("weights") or {}).items():
            if k in sl.CRITERIA_KEYS:
                weights[k] = float(v)
        p.criteria_weights = weights
        db.commit()
        sl.rescore_candidates(db, user, search)
        return {"ok": True, "weights": weights}, True

    if name == "set_filter":
        p = _profile(db, user)
        filters = dict(p.filters or {})
        for k in ("language_ease", "climate", "visa"):
            if k in args:
                v = args[k]
                if v in (None, False, ""):
                    filters.pop(k, None)
                else:
                    filters[k] = v
        p.filters = filters
        db.commit()
        sl.build_instant_shortlist(db, user, search)
        return {"ok": True, "filters": filters}, True

    if name == "add_country":
        place = _find_place(db, args.get("name", ""))
        if place is None:
            try:
                place = place_research.research_place(db, args.get("name", ""), user_id=user.id)
            except ai_client.AIUnavailable:
                return {"ok": False, "error": "research unavailable"}, False
        if place is None:
            return {"ok": False, "error": "country not found"}, False
        cand = (
            db.query(Candidate)
            .filter(Candidate.search_id == search.id, Candidate.place_id == place.id)
            .first()
        )
        if cand:
            cand.status = "active"
        else:
            cand = Candidate(
                search_id=search.id, place_id=place.id, per_criterion=place.attributes or {},
                selected=_selected_count(db, search.id) < sl.MAX_COMPARE,
            )
            db.add(cand)
        db.commit()
        # Score the new candidate against the profile so it ranks and shows a match score
        # like every other row (a bare insert leaves match_score null → blank, bottom row).
        sl.rescore_candidates(db, user, search)
        return {"ok": True, "added": place.name, "selected": cand.selected}, True

    if name == "select_country":
        place = _find_place(db, args.get("name", ""))
        cand = (
            db.query(Candidate).filter(
                Candidate.search_id == search.id, Candidate.place_id == place.id).first()
            if place else None
        )
        if not cand:
            return {"ok": False, "error": "not in this search"}, False
        want = bool(args.get("selected"))
        if want and not cand.selected and _selected_count(db, search.id) >= sl.MAX_COMPARE:
            return {"ok": False, "error": f"already {sl.MAX_COMPARE} selected"}, False
        cand.selected = want
        db.commit()
        return {"ok": True, "name": place.name, "selected": want}, True

    if name == "rebuild_shortlist":
        sl.build_instant_shortlist(db, user, search)
        return {"ok": True}, True

    return {"ok": False, "error": f"unknown tool {name}"}, False
