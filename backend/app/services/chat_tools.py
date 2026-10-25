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
from app.services import ai_client, criteria, criterion_eval, place_research
from app.services import shortlist as sl

_CRITERIA = ", ".join(criteria.criteria_keys())

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
        "name": "set_comparison",
        "description": (
            "Replace the comparison board with a specific set of countries (English names, "
            "up to 5). Researches any not yet known, then adds and selects exactly these "
            "and re-ranks. ALWAYS call this when you propose a new set of countries, so your "
            "proposal actually appears in the table instead of only in your message."
        ),
        "parameters": {
            "type": "object",
            "properties": {"countries": {"type": "array", "items": {"type": "string"}}},
            "required": ["countries"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "add_custom_criterion",
        "description": (
            "Add a user-defined criterion the built-in list doesn't cover (e.g. "
            "'vegan-friendly', 'good surfing', 'startup ecosystem'). The AI scores each "
            "country on it and it joins the comparison and ranking."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "Short name for the table column (1-3 words)."},
                "description": {"type": "string", "description": "Longer explanation of what to evaluate, used to prompt the AI."},
            },
            "required": ["label"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "explain_country",
        "description": (
            "READ-ONLY. Why a country is or isn't in the user's top 5, from the app's real scores: "
            "its rank, score, any hard filter excluding it (with the user's minimum and the "
            "country's value), and the criteria where it loses or gains the most points against "
            "the user's #5. ALWAYS call this before explaining why a country ranks where it does "
            "(e.g. 'why didn't Spain come up?'), and base your explanation ONLY on its result. "
            "English country name."
        ),
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_ranking",
        "description": (
            "READ-ONLY. The full ranking of countries for this search (best first): score, "
            "whether it's on the board, and any hard filters it fails. Use it to answer "
            "'what comes next?', 'where does X rank?' or to find good options off the board."
        ),
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 40}},
            "required": [],
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
    name = (name or "").strip()
    q = db.query(Place).filter(Place.kind == "country")
    return (q.filter(Place.name.ilike(name)).first()
            or (q.filter(Place.iso_code.ilike(name)).first() if len(name) == 2 else None))


def _violations(db: Session, user: User, search: Search, place: Place) -> list[str]:
    """Which active hard filters this place fails (so the assistant can flag it). Same values
    as the board, including the per-user visa/residency layer."""
    custom_defs = search.custom_criteria or []
    eval_keys = criteria.objective_keys() + [c["key"] for c in custom_defs if c.get("key")]
    evals = sl._place_evals(db, place.id, user.profile, eval_keys)
    return sl.filter_status(place, user.profile, evals, custom_defs)["violations"]


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
            if k in criteria.criteria_keys():
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
        sl.repopulate_board(db, user, search)
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
        # Score now; any missing cells fill in progressively via /evaluate-pending.
        sl.rescore_candidates(db, user, search)
        return {"ok": True, "added": place.name, "selected": cand.selected,
                "filter_violations": _violations(db, user, search, place)}, True

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

    if name == "add_custom_criterion":
        label = (args.get("label") or "").strip()
        if not label:
            return {"ok": False, "error": "missing label"}, False
        key = criterion_eval.slugify(label)
        defs = list(search.custom_criteria or [])
        new_def = {"key": key, "label": label, "description": args.get("description"), "weight": 1.0}
        if not any(c.get("key") == key for c in defs):
            defs.append(new_def)
            search.custom_criteria = defs
        if key not in (search.criteria_set or []):
            search.criteria_set = [*(search.criteria_set or []), key]
        db.commit()
        from app.services import custom_criteria
        custom_criteria.persist_to_profile(db, user, [new_def])  # follow the user across searches
        # Per-country evaluation fills in progressively via /evaluate-pending (non-blocking).
        return {"ok": True, "added_criterion": label}, True

    if name == "set_comparison":
        names = [str(n).strip() for n in (args.get("countries") or []) if str(n).strip()]
        names = names[: sl.MAX_COMPARE]
        if not names:
            return {"ok": False, "error": "no countries provided"}, False
        target_ids: list[int] = []
        applied: list[str] = []
        target_places: list[Place] = []
        for nm in names:
            place = _find_place(db, nm)
            if place is None:
                try:
                    place = place_research.research_place(db, nm, user_id=user.id)
                except ai_client.AIUnavailable:
                    place = None
            if place is None:
                continue
            cand = (
                db.query(Candidate)
                .filter(Candidate.search_id == search.id, Candidate.place_id == place.id)
                .first()
            )
            if cand:
                cand.status = "active"
            else:
                cand = Candidate(search_id=search.id, place_id=place.id,
                                 per_criterion=place.attributes or {}, selected=True)
                db.add(cand)
            target_ids.append(place.id)
            applied.append(place.name)
            target_places.append(place)
        # Make the board exactly this set: select the targets, deselect the rest.
        for c in (
            db.query(Candidate)
            .filter(Candidate.search_id == search.id, Candidate.status == "active")
            .all()
        ):
            c.selected = c.place_id in target_ids
        db.commit()
        # Score now; missing cells fill in progressively via /evaluate-pending.
        sl.rescore_candidates(db, user, search)
        # Report any that break the user's active filters so the assistant can flag them.
        violating = {
            p.name: v for p in target_places if (v := _violations(db, user, search, p))
        }
        return {"ok": True, "countries": applied, "filter_violations": violating}, True

    if name == "explain_country":
        place = _find_place(db, args.get("name", ""))
        if place is None:
            return {"ok": False, "error": f"unknown country {args.get('name')!r} (use the English name)"}, False
        return {"ok": True, **sl.why_not(db, user, search, place)}, False

    if name == "get_ranking":
        limit = max(1, min(40, int(args.get("limit") or 15)))
        rows = sl.rank_all(db, user, search)
        return {"ok": True, "total": len(rows), "ranking": [
            {"rank": i + 1, "name": r["name"], "score": r["score"], "on_board": r["on_board"],
             "fails_filters": r["violations"]}
            for i, r in enumerate(rows[:limit])
        ]}, False

    if name == "rebuild_shortlist":
        sl.repopulate_board(db, user, search)
        return {"ok": True}, True

    return {"ok": False, "error": f"unknown tool {name}"}, False
