# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Shared per-place "criteria view" for the comparison board: the colour tiers,
justifications, custom-criterion levels and the list of still-pending cells. Used for both
the candidate columns and the baseline (current-country) column so they render identically.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.place import Place
from app.models.profile import Profile
from app.services import comparison, criteria, criterion_eval
from app.services import shortlist as sl


def criteria_view(
    db: Session, place: Place, profile: Profile | None, custom_defs: list | None, locale: str,
) -> dict:
    custom_keys = [c["key"] for c in (custom_defs or []) if c.get("key")]
    eval_keys = criteria.OBJECTIVE_KEYS + custom_keys
    attrs = place.attributes or {}
    rows = criterion_eval.evals_for_place(db, place.id, eval_keys)
    evals = {k: criterion_eval.value_of(ev) for k, ev in rows.items()}

    # Colour tier for EVERY criterion (built-in + custom) computed the same way — from its
    # 0-1 value (eval, else seed bucket, else neutral). No built-in/custom branch.
    all_keys = list(sl.CRITERIA_KEYS) + custom_keys
    quality = {k: sl.quality_tier(sl._criterion_value(k, attrs, profile, place, evals)) for k in all_keys}
    # Templated reason for computed criteria; eval-based (score + justification) wherever a
    # cached evaluation exists; a "pending" marker for any criterion with no value yet.
    reasons = {k: comparison.criterion_reason(place, profile, k) for k in sl.CRITERIA_KEYS}
    pending: list[str] = []
    for key in eval_keys:
        ev = rows.get(key)
        if ev is not None:
            reasons[key] = criterion_eval.reason_from_eval(ev, locale)
        elif not attrs.get(key):  # no eval and no seed bucket → still being evaluated
            reasons[key] = {"code": "custom_pending"}
            pending.append(key)
    return {"quality": quality, "reasons": reasons, "pending": pending}


def criterion_details(
    db: Session, place: Place, profile: Profile | None, custom_defs: list | None,
    lang: str, legacy: dict | None,
) -> list[dict]:
    """One uniform per-criterion detail list for the drill-down — built-in AND custom
    criteria treated identically: every entry has a 0-100 score (the same value the summary
    table shows), a justification and sources. Justification comes from the unified eval
    cache when present, else the legacy long-form `criteria_detail` text."""
    custom_lookup = {c["key"]: c for c in (custom_defs or []) if c.get("key")}
    custom_keys = list(custom_lookup.keys())
    eval_keys = criteria.OBJECTIVE_KEYS + custom_keys
    rows = criterion_eval.evals_for_place(db, place.id, eval_keys)
    eval_values = {k: criterion_eval.value_of(ev) for k, ev in rows.items()}
    legacy_map = {d["key"]: d for d in (legacy or {}).get("criteria", [])}
    attrs = place.attributes or {}

    out: list[dict] = []
    for key in list(sl.CRITERIA_KEYS) + custom_keys:
        score = round(sl._criterion_value(key, attrs, profile, place, eval_values) * 100)
        ev = rows.get(key)
        if ev is not None:
            summary = (ev.summary_fr if lang == "fr" else ev.summary_en) or ev.summary_en or ev.summary_fr or ""
            sources = ev.sources or []
        else:
            ld = legacy_map.get(key) or {}
            summary, sources = ld.get("summary", ""), ld.get("sources", [])
        out.append({
            "key": key, "label": custom_lookup.get(key, {}).get("label"),
            "score": score, "summary": summary, "sources": sources,
        })
    return out
