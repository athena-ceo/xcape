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
from app.services import comparison, criteria, criterion_eval, place_research
from app.services import shortlist as sl


def criteria_view(
    db: Session, place: Place, profile: Profile | None, custom_defs: list | None,
) -> dict:
    custom_keys = [c["key"] for c in (custom_defs or []) if c.get("key")]
    eval_keys = criteria.objective_keys() + custom_keys
    attrs = place.attributes or {}
    rows = criterion_eval.evals_for_place(db, place.id, eval_keys)
    evals = {k: criterion_eval.value_of(ev) for k, ev in rows.items()}

    # Colour tier for EVERY criterion (built-in + custom) computed the same way — from its
    # 0-1 value (eval, else seed bucket, else neutral). No built-in/custom branch.
    all_keys = list(criteria.criteria_keys()) + custom_keys
    quality = {k: sl.quality_tier(sl._criterion_value(k, attrs, profile, place, evals)) for k in all_keys}
    # Templated reason for computed criteria; eval-based (score + justification) wherever a
    # cached evaluation exists; a "pending" marker for any criterion with no value yet.
    reasons = {k: comparison.criterion_reason(place, profile, k) for k in criteria.criteria_keys()}
    pending: list[str] = []
    for key in eval_keys:
        ev = rows.get(key)
        if ev is not None:
            reasons[key] = criterion_eval.reason_from_eval(ev)
        elif not attrs.get(key):  # no eval and no seed bucket → still being evaluated
            reasons[key] = {"code": "custom_pending"}
            pending.append(key)
    return {"quality": quality, "reasons": reasons, "pending": pending}


def criterion_details(
    db: Session, place: Place, profile: Profile | None, custom_defs: list | None,
    lang: str,
) -> list[dict]:
    """Per-criterion detail for the drill-down — assembled from caches only, NO AI calls.

    Each row carries `pending: True` until its explanation text exists, so the page can show
    boxes immediately and fill them progressively (see /detail/generate):
    - objective & custom criteria: text + score come from the cached AI eval (place_custom_evals);
      pending until evaluated (score stays None so we never show a bucket-derived number);
    - computed criteria (cost, climate, language, visa, inclusion): score is deterministic from
      the profile (always shown); text comes from the per-key `place.criteria_detail` cache,
      pending until generated;
    - proximity: synthesised distance explanation, never pending."""
    custom_lookup = {c["key"]: c for c in (custom_defs or []) if c.get("key")}
    custom_keys = list(custom_lookup.keys())
    eval_objective_keys = set(criteria.objective_keys()) | set(custom_keys)
    rows = criterion_eval.evals_for_place(db, place.id, list(eval_objective_keys))
    eval_values = {k: criterion_eval.value_of(ev) for k, ev in rows.items()}
    detail = place_research.detail_map(place)
    attrs = place.attributes or {}

    out: list[dict] = []
    for key in list(criteria.criteria_keys()) + custom_keys:
        value = sl._criterion_value(key, attrs, profile, place, eval_values)
        ev = rows.get(key)
        summary, sources, score, pending = "", [], None, False
        if key in eval_objective_keys:
            if ev is not None:
                summary = (ev.summary_fr if lang == "fr" else ev.summary_en) or ev.summary_en or ev.summary_fr or ""
                sources = ev.sources or []
                score = round(value * 100)
            else:
                pending = True  # no AI eval yet → generate on demand
        elif key == "proximity":
            summary = _proximity_summary(profile, place, lang)
            score = round(value * 100)
        else:  # computed criterion: deterministic score now, AI text lazily
            score = round(value * 100)
            d = detail.get(key)
            if d:
                summary = (d.get(f"summary_{lang}") or d.get("summary_en")
                           or d.get("summary_fr") or d.get("summary") or "")
                sources = d.get("sources", [])
            if not summary:
                pending = True
        out.append({
            "key": key, "label": custom_lookup.get(key, {}).get("label"),
            "score": score, "summary": summary, "sources": sources, "pending": pending,
        })
    return out


def _proximity_summary(profile: Profile | None, place: Place, lang: str) -> str:
    """A distance-based justification for proximity (no AI). Travel time is a rough flight
    estimate; cost is noted as not yet estimated."""
    from app.services import geo

    origin = profile.user.current_country if (profile and profile.user) else None
    km = geo.distance_between(origin, (place.iso_code or "") if place else "")
    if km is None:
        return ""
    km_r = int(round(km / 50.0) * 50)
    hours = round(km / 800.0 + 1.5)  # cruise ~800 km/h + ground time
    if lang == "fr":
        return (f"≈ {km_r} km de {origin or 'votre pays'} (~{hours} h de vol). "
                f"Coût du trajet : non estimé pour l'instant.")
    return (f"≈ {km_r} km from {origin or 'your country'} (~{hours} h by air). "
            f"Travel cost: not yet estimated.")
