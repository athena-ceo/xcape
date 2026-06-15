# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Instant, seed-driven shortlist — no AI call.

Scores every country Place against the user's profile so the first results appear with
zero latency. The score blends per-criterion quality with the user's stated priorities:

- baseline weights, overridden by the user's explicit criteria_weights;
- weight boosts derived from *why they are leaving* (so we avoid places with the same
  problem — e.g. leaving for political reasons up-weights political_stability);
- household adjustments (families care more about healthcare & safety);
- climate preference matching and language-learning willingness.

AI-based discrimination refines this list later (build phase 3).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.place import Place
from app.models.profile import Profile
from app.models.search import Search
from app.models.user import User
from app.services import criteria
from app.services import geo

SHORTLIST_SIZE = 15
MAX_COMPARE = 5  # how many candidates can sit in the comparison board at once

# Ordinal scales, criteria keys and default weights all come from the registry
# (criteria.scales()/criteria_keys()/default_weights()) — read live so admin edits and
# deactivations take effect without a restart.

# Social-acceptance levels per community (used by the inclusion criterion) and the
# general-openness fallback when the user named no specific community.
_GROUP_SCALE = {"high": 1.0, "mixed": 0.5, "low": 0.15}
_OPENNESS_SCALE = {"high": 1.0, "medium": 0.55, "low": 0.15}
# Proximity bands (great-circle distance from the user's current country, km).
_PROXIMITY_NEAR_KM = 1500
_PROXIMITY_FAR_KM = 6000

# Picking a reason/priority that carries a tag up-weights every leaf carrying that tag —
# so "fear" lifts the whole protection cluster, "financial" the money cluster, etc.
_TAG_BOOST = 1.2

# Human-readable reason labels (FR/EN) for the criteria that drove a high score.
_REASON_LABELS: dict[str, dict[str, str]] = {
    "cost_of_living": {"fr": "coût de la vie abordable", "en": "affordable cost of living"},
    "healthcare": {"fr": "système de santé solide", "en": "strong healthcare"},
    "safety": {"fr": "sécurité élevée", "en": "high safety"},
    "political_stability": {"fr": "stabilité politique", "en": "political stability"},
    "tax": {"fr": "fiscalité douce", "en": "light taxation"},
    "visa": {"fr": "visa accessible", "en": "accessible visa"},
    "language_ease": {"fr": "langue accessible", "en": "manageable language"},
    "climate": {"fr": "climat qui vous convient", "en": "climate that suits you"},
    "inclusion": {"fr": "tolérance et accueil", "en": "tolerance and acceptance"},
    "gender_equality": {"fr": "égalité femmes-hommes", "en": "gender equality"},
    "culture": {"fr": "vie culturelle riche", "en": "rich cultural life"},
    "food": {"fr": "culture culinaire", "en": "food culture"},
    "expat_community": {"fr": "communauté d'expatriés", "en": "expat community"},
    "nature": {"fr": "nature et paysages", "en": "nature and landscapes"},
}


def _effective_weights(profile: Profile | None) -> dict[str, float]:
    if not profile:
        return dict(criteria.default_weights())
    # The user's persona (relocation archetype) supplies the base weight profile — only its
    # critical criteria carry weight, the rest stay 0 (genuinely unimportant) so the ranking is
    # discriminating. Without a persona, fall back to the flat defaults + tag-driven boosts.
    persona_key = getattr(profile, "persona", None)
    persona_w = criteria.persona_weights(persona_key)
    if persona_w:
        weights = dict(persona_w)
    else:
        weights = dict(criteria.default_weights())
        # Tag-driven prioritisation: the user's reasons/priorities map to tags, and any leaf
        # carrying a selected tag is up-weighted — so "fear" lifts the protection cluster, etc.
        selected_tags = criteria.tags_for_reasons(profile.reasons_leaving)
        if selected_tags:
            for key, tags in criteria.leaf_tags().items():
                if selected_tags.intersection(tags):
                    weights[key] = weights.get(key, 0.0) + _TAG_BOOST
    if profile.household_type == "family":
        weights["healthcare"] = weights.get("healthcare", 0) + 0.5
        weights["safety"] = weights.get("safety", 0) + 0.5
    # Education only matters for families, or couples planning children. It is not in the
    # baseline weights, so singles / childless couples don't score on it at all.
    if profile.household_type == "family" or (
        profile.household_type == "couple" and getattr(profile, "intends_children", False)
    ):
        weights["education"] = weights.get("education", 0) + 1.5
    # If the user named communities whose acceptance matters to them, inclusion becomes
    # a strong factor (they care about feeling welcome, not just averages).
    if getattr(profile, "minority_groups", None):
        weights["inclusion"] = weights.get("inclusion", 0) + 1.5
    if profile.criteria_weights:
        for key, value in profile.criteria_weights.items():
            weights[key] = float(value)
    return weights


# EU/EEA + Switzerland — the freedom-of-movement zone: citizens of any of these can
# settle in any other with no visa. iso 3166-1 alpha-2.
_EU_FOM = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE",
    "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
    "IS", "LI", "NO", "CH",
}


def _single_citizenship_visa(citizenship: str, dest: str, base: float) -> float:
    """Ease of settling for ONE citizenship."""
    if dest and citizenship == dest:
        return 1.0  # citizen of the destination
    if dest in _EU_FOM:
        return 1.0 if citizenship in _EU_FOM else 0.3  # EU free movement, else hard
    return base


def _visa_value(attrs: dict, profile: Profile | None, place: Place | None) -> float:
    """Ease of moving the whole household there, given its citizenships (not residence).

    Uses the MOST RESTRICTIVE citizenship — everyone must be able to settle, so a French
    + American household is judged by the American passport, not the French one.
    """
    citz = (
        {str(c).upper() for c in (profile.user.citizenships or [])}
        if (profile and profile.user and profile.user.citizenships)
        else set()
    )
    base = criteria.scales().get("visa", {}).get(str(attrs.get("visa", "")).lower(), 0.5)
    if not citz:
        return base  # citizenship unknown — fall back to general accessibility
    dest = (place.iso_code or "").upper() if place else ""
    return min(_single_citizenship_visa(c, dest, base) for c in citz)


# Coarse monthly cost of living for one person (EUR), by symbolic level — a proxy used
# to score affordability against the user's budget. The per-country AI drill-down gives
# real figures; this only needs to rank countries sensibly relative to a budget.
_COST_BAND = {"low": 1200, "medium": 2200, "high": 3500}
_HOUSEHOLD_FACTOR = {"single": 1.0, "couple": 1.6, "family": 2.4}


def _cost_value(attrs: dict, profile: Profile | None) -> float:
    """Affordability of the cost of living given the user's budget + household.

    With a budget set, score how comfortably it covers the estimated cost; without one,
    fall back to the plain symbolic scale (cheaper = better).
    """
    level = str(attrs.get("cost_of_living", "")).lower()
    budget = getattr(profile, "budget_monthly", None) if profile else None
    if budget and level in _COST_BAND:
        factor = _HOUSEHOLD_FACTOR.get(getattr(profile, "household_type", None), 1.3)
        estimate = _COST_BAND[level] * factor
        ratio = budget / estimate
        # ratio 0.5 (budget half the cost) -> 0; ratio 1.2 (comfortable surplus) -> 1.
        return max(0.0, min(1.0, (ratio - 0.5) / 0.7))
    return criteria.scales().get("cost_of_living", {}).get(level, 0.5)


def _inclusion_value(attrs: dict, profile: Profile | None) -> float:
    """How welcome the user would feel. Judged by the WORST-accepting of the communities
    they said matter to them (a place hostile to even one shouldn't look safe); when they
    named none, fall back to the country's general societal openness.
    """
    groups = (getattr(profile, "minority_groups", None) or []) if profile else []
    acceptance = attrs.get("social_acceptance") or {}
    openness = _OPENNESS_SCALE.get(str(attrs.get("openness", "")).lower(), 0.5)
    if groups:
        # Preset communities use their specific acceptance level; free-text or
        # not-yet-assessed ones fall back to the country's general openness.
        return min(_GROUP_SCALE.get(str(acceptance.get(g, "")).lower(), openness) for g in groups)
    return openness


def _proximity_value(profile: Profile | None, place: Place | None) -> float:
    """How close the candidate is to the user's current country (great-circle distance),
    banded near→far. Neutral 0.5 when either centroid is unknown."""
    origin = (profile.user.current_country if (profile and profile.user) else None)
    dest_iso = (place.iso_code or "") if place else ""
    d = geo.distance_between(origin, dest_iso)
    if d is None:
        return 0.5
    if d <= _PROXIMITY_NEAR_KM:
        return 1.0
    if d >= _PROXIMITY_FAR_KM:
        return 0.2
    span = _PROXIMITY_FAR_KM - _PROXIMITY_NEAR_KM
    return round(1.0 - 0.8 * (d - _PROXIMITY_NEAR_KM) / span, 3)


def _criterion_value(
    key: str, attrs: dict, profile: Profile | None, place: Place | None = None,
    evals: dict[str, float] | None = None,
) -> float:
    # Objective + custom criteria: prefer the cached AI eval (0-1) when we have one; this is
    # how the ~190 seed-sparse countries get real values. Computed criteria fall through.
    if evals is not None and key in evals:
        return float(evals[key])
    if key == "visa":
        return _visa_value(attrs, profile, place)
    if key == "cost_of_living":
        return _cost_value(attrs, profile)
    if key == "inclusion":
        return _inclusion_value(attrs, profile)
    if key == "proximity":
        return _proximity_value(profile, place)
    if key == "climate":
        pref = profile.climate_pref if profile else None
        return 1.0 if (pref and attrs.get("climate") == pref) else 0.5
    if key == "language_ease":
        skills = (profile.language_skills or {}) if profile else {}
        known = {str(lang).lower() for lang in (skills.get("known") or [])}
        willing = bool(skills.get("willing_to_learn"))
        country_langs = {str(lang).lower() for lang in (attrs.get("languages") or [])}
        # You already speak a language used there — best possible fit.
        if known and country_langs and (known & country_langs):
            return 1.0
        # You don't speak any local language. Fall back to how learnable it is, softened
        # if willing to learn. Default to "hard" (0.3) when the difficulty is unknown —
        # an unknown language you don't speak shouldn't be treated as middling.
        base = criteria.scales().get("language_ease", {}).get(str(attrs.get(key, "")).lower(), 0.3)
        if willing:
            return min(1.0, base + 0.2)
        return round(base * 0.7, 3)
    # Objective (AI-scored) criteria: the AI eval is authoritative. Without one, do NOT trust
    # the coarse seed bucket (high=1.0) — it's on a far more optimistic scale than real evals
    # (~0.5 avg) and would let an un-evaluated country leap to the top. Treat it as a neutral
    # provisional value until a real eval lands.
    if key in criteria.objective_keys():
        return 0.5
    scale = criteria.scales().get(key, {})
    return scale.get(str(attrs.get(key, "")).lower(), 0.5)


def quality_tier(value: float) -> str:
    """Map a 0-1 criterion value to a colour tier: good / ok / bad."""
    return "good" if value >= 0.7 else ("ok" if value >= 0.45 else "bad")


def candidate_quality(
    place: Place, profile: Profile | None, evals: dict[str, float] | None = None,
) -> dict[str, str]:
    """Per-criterion colour tier for a place, from the user's perspective."""
    attrs = place.attributes or {}
    return {k: quality_tier(_criterion_value(k, attrs, profile, place, evals)) for k in criteria.criteria_keys()}


# Quality tiers map to minimum 0-1 thresholds (matches quality_tier cutoffs).
_TIER_THRESHOLD = {"good": 0.7, "ok": 0.45, "any": 0.0}


def _threshold(fval) -> float:
    """A filter value as a minimum 0-1 threshold. Accepts a raw number or a tier word."""
    if isinstance(fval, bool):
        return 0.7  # a bare True on a generic criterion means "must be good"
    if isinstance(fval, (int, float)):
        return float(fval)
    return _TIER_THRESHOLD.get(str(fval).lower(), 0.7)


def filter_status(
    place: Place, profile: Profile | None,
    evals: dict[str, float] | None = None,
    custom_defs: list[dict] | None = None,
) -> dict[str, list[str]]:
    """Per-place hard-filter result against the user's active filters.

    Returns {"violations": [...], "pending": [...]}: a place QUALIFIES when both are
    empty. `pending` holds criteria whose AI score hasn't been computed yet (objective
    built-ins or custom criteria with no cached eval) — they can't be judged now and are
    re-checked once the eval lands (progressive fill). Everything else either passes or
    is a violation.
    """
    filters = (profile.filters or {}) if profile else {}
    attrs = place.attributes or {}
    evals = evals or {}
    objective = set(criteria.objective_keys())
    violations: list[str] = []
    pending: list[str] = []

    for key, fval in filters.items():
        if fval in (None, "", False) or (isinstance(fval, list) and not fval):
            continue
        if key == "language_ease":
            known = {str(x).lower() for x in (profile.language_skills or {}).get("known", [])} if profile else set()
            langs = {str(x).lower() for x in (attrs.get("languages") or [])}
            if not (known and langs and (known & langs)):
                violations.append(key)
        elif key == "climate":
            allowed = fval if isinstance(fval, list) else [fval]
            if attrs.get("climate") not in allowed:
                violations.append(key)
        elif key == "visa":
            if _visa_value(attrs, profile, place) < 0.9:
                violations.append(key)
        elif key == "inclusion":
            if _inclusion_value(attrs, profile) < 0.5:
                violations.append(key)
        else:
            # Generic minimum on any other criterion. Objective criteria are AI-scored, so
            # require a cached eval — without one we can't judge yet (pending). Computed
            # criteria (cost, proximity) resolve synchronously.
            if key in objective and key not in evals:
                pending.append(key)
                continue
            if _criterion_value(key, attrs, profile, place, evals) < _threshold(fval):
                violations.append(key)

    # Custom-criterion minimums live per-search on the criterion definition.
    for c in custom_defs or []:
        k, mn = c.get("key"), c.get("min")
        if not k or mn in (None, "", False):
            continue
        if k not in evals:
            pending.append(k)
        elif float(evals[k]) < _threshold(mn):
            violations.append(k)

    return {"violations": violations, "pending": pending}


def passes_filters(
    place: Place, profile: Profile | None,
    evals: dict[str, float] | None = None,
    custom_defs: list[dict] | None = None,
) -> bool:
    """True when a place satisfies every active filter (and none are pending)."""
    st = filter_status(place, profile, evals, custom_defs)
    return not st["violations"] and not st["pending"]


def _score_place(
    place: Place, weights: dict[str, float], profile: Profile | None,
    evals: dict[str, float] | None = None,
):
    attrs = place.attributes or {}
    total = wsum = 0.0
    contributions: list[tuple[str, float]] = []
    for key, weight in weights.items():
        if weight <= 0:
            continue
        val = _criterion_value(key, attrs, profile, place, evals)
        total += val * weight
        wsum += weight
        contributions.append((key, val * weight))
    score = round(100 * total / wsum, 1) if wsum else 0.0
    locale = "fr"
    if profile and profile.user:
        locale = profile.user.locale or "fr"
    top = sorted(contributions, key=lambda t: t[1], reverse=True)[:3]
    reasons = [
        _REASON_LABELS[k][locale]
        for k, v in top
        if k in _REASON_LABELS and _criterion_value(k, attrs, profile, place, evals) >= 0.7
    ]
    return score, reasons


def rescore_candidates(db: Session, user: User, search: Search) -> list[Candidate]:
    """Recompute score/reasons/rank for a search's existing candidates against the
    current profile, preserving membership and selection. Used after profile edits.
    """
    profile = user.profile
    weights = _effective_weights(profile)
    # Fold in any user-defined criteria for this search (each has its own weight).
    from app.services import criteria, criterion_eval  # avoid circular import at module load

    custom_defs = search.custom_criteria or []
    for c in custom_defs:
        if c.get("key"):
            weights[c["key"]] = float(c.get("weight", 1.0))
    custom_keys = [c["key"] for c in custom_defs if c.get("key")]
    # Cached AI evals cover objective built-ins (safety, tax, …) + the custom criteria.
    eval_keys = criteria.objective_keys() + custom_keys

    candidates = (
        db.query(Candidate)
        .filter(Candidate.search_id == search.id, Candidate.status == "active")
        .all()
    )
    scorable = [c for c in candidates if c.place]
    for cand in scorable:
        evals = criterion_eval.values_for_place(db, cand.place_id, eval_keys)
        score, reasons = _score_place(cand.place, weights, profile, evals)
        cand.match_score = score
        cand.match_reasons = reasons
    for rank, cand in enumerate(
        sorted(scorable, key=lambda c: c.match_score or 0, reverse=True), start=1
    ):
        cand.rank = rank
    db.commit()
    for cand in candidates:
        db.refresh(cand)
    return candidates


def explain_candidate(db: Session, user: User, candidate: Candidate) -> dict:
    """Break down how a candidate's score was derived: each weighted criterion's
    quality (0-100), its weight, and the contribution it adds to the final score.
    Contributions sum to the score.
    """
    from app.services import criteria, criterion_eval  # avoid circular import at module load

    profile = user.profile
    weights = _effective_weights(profile)
    place = candidate.place
    attrs = (place.attributes or {}) if place else {}
    prioritized = set((profile.criteria_weights or {}).keys()) if profile else set()

    # Include the search's custom criteria weights + cached evals, matching rescore.
    search = db.get(Search, candidate.search_id)
    custom_defs = (search.custom_criteria or []) if search else []
    for c in custom_defs:
        if c.get("key"):
            weights[c["key"]] = float(c.get("weight", 1.0))
    eval_keys = criteria.objective_keys() + [c["key"] for c in custom_defs if c.get("key")]
    evals = criterion_eval.values_for_place(db, candidate.place_id, eval_keys) if place else {}

    active = {k: w for k, w in weights.items() if w > 0}
    wsum = sum(active.values())
    rows = []
    for key, weight in active.items():
        quality = _criterion_value(key, attrs, profile, place, evals)
        rows.append({
            "key": key,
            "quality": round(quality * 100),       # how good this country is on this criterion
            "weight": round(weight, 2),            # how much the user cares
            "contribution": round(100 * quality * weight / wsum, 1) if wsum else 0,
            "prioritized": key in prioritized,
        })
    rows.sort(key=lambda r: r["contribution"], reverse=True)
    score = round(sum(r["contribution"] for r in rows), 1)
    return {"score": score, "weight_total": round(wsum, 2), "rows": rows}


def build_instant_shortlist(db: Session, user: User, search: Search) -> list[Candidate]:
    from app.services import criteria, criterion_eval  # avoid circular import at module load

    profile = user.profile
    weights = _effective_weights(profile)

    countries = db.query(Place).filter(Place.kind == "country", Place.active.is_(True)).all()
    # Apply hard filters (e.g. "must speak a language I know"); if filters exclude
    # everything, fall back to the unfiltered pool so the user still sees options. (The
    # board's top-up-with-flagged-extras behaviour lives in repopulate_board, used when the
    # user edits criteria later.)
    qualified = [p for p in countries if passes_filters(p, profile)]
    pool = qualified or countries
    # Batch-load the cached AI evals for the whole pool so the seed-sparse countries score
    # on real values (one query, not one per country).
    evals_by_place = criterion_eval.values_for_places(
        db, [p.id for p in pool], criteria.objective_keys()
    )
    scored = sorted(
        ((p, *_score_place(p, weights, profile, evals_by_place.get(p.id))) for p in pool),
        key=lambda t: t[1],
        reverse=True,
    )[:SHORTLIST_SIZE]

    db.query(Candidate).filter(Candidate.search_id == search.id).delete()

    candidates: list[Candidate] = []
    for rank, (place, score, reasons) in enumerate(scored, start=1):
        cand = Candidate(
            search_id=search.id,
            place_id=place.id,
            match_score=score,
            match_reasons=reasons,
            rank=rank,
            selected=rank <= MAX_COMPARE,  # default: top 5 pre-selected for comparison
            per_criterion=place.attributes or {},
        )
        db.add(cand)
        candidates.append(cand)
    db.commit()
    for cand in candidates:
        db.refresh(cand)
    return candidates


def repopulate_board(db: Session, user: User, search: Search) -> list[Candidate]:
    """Rebuild the list respecting the current weights + hard filters, without throwing
    away the user's curated board.

    - the user's currently-selected countries stay selected (re-scored; flagged in the UI
      if they now violate a filter — we never auto-remove them);
    - the selected board is topped up to MAX_COMPARE from the best candidates, preferring
      filter-qualifying ones, then pending, then (flagged) violating — so a strict filter
      still yields a full board instead of an empty one;
    - the unselected suggestion pool is refreshed to SHORTLIST_SIZE from the current
      ranking. Idempotent and non-destructive of selections, so it's safe to call again
      after async custom/objective evals land (the progressive-fill iteration).
    """
    from app.services import criteria, criterion_eval  # avoid circular import at module load

    profile = user.profile
    weights = _effective_weights(profile)
    custom_defs = list(search.custom_criteria or [])
    for c in custom_defs:
        if c.get("key"):
            weights[c["key"]] = float(c.get("weight", 1.0))
    eval_keys = criteria.objective_keys() + [c["key"] for c in custom_defs if c.get("key")]

    countries = db.query(Place).filter(Place.kind == "country", Place.active.is_(True)).all()
    evals_by_place = criterion_eval.values_for_places(db, [p.id for p in countries], eval_keys)

    # Score + filter-classify every country; rank qualified → pending → violating, by score.
    scored = []  # (place, score, reasons, tier)
    for p in countries:
        evals = evals_by_place.get(p.id)
        score, reasons = _score_place(p, weights, profile, evals)
        st = filter_status(p, profile, evals, custom_defs)
        tier = 0 if not st["violations"] and not st["pending"] else (1 if not st["violations"] else 2)
        scored.append((p, score, reasons, tier))
    scored.sort(key=lambda t: (t[3], -t[1]))

    existing = {
        c.place_id: c
        for c in db.query(Candidate)
        .filter(Candidate.search_id == search.id, Candidate.status == "active")
        .all()
    }
    selected_ids = {pid for pid, c in existing.items() if c.selected}

    # Keep current selections; top up to MAX_COMPARE from the best-ranked remainder.
    final_selected = set(selected_ids)
    for p, _s, _r, _t in scored:
        if len(final_selected) >= MAX_COMPARE:
            break
        final_selected.add(p.id)
    # Suggestion pool: best-ranked not-selected, up to SHORTLIST_SIZE.
    suggestions = [p.id for p, _s, _r, _t in scored if p.id not in final_selected][:SHORTLIST_SIZE]
    target_ids = final_selected | set(suggestions)

    # Drop stale suggestions (anything not selected and no longer in the pool).
    for pid, cand in existing.items():
        if pid not in target_ids:
            db.delete(cand)

    # Upsert the target set with fresh scores + selection.
    for p, score, reasons, _t in scored:
        if p.id not in target_ids:
            continue
        cand = existing.get(p.id)
        if cand is None:
            cand = Candidate(search_id=search.id, place_id=p.id, per_criterion=p.attributes or {})
            db.add(cand)
        cand.status = "active"
        cand.match_score = score
        cand.match_reasons = reasons
        cand.selected = p.id in final_selected
    db.commit()

    candidates = (
        db.query(Candidate)
        .filter(Candidate.search_id == search.id, Candidate.status == "active")
        .all()
    )
    for rank, cand in enumerate(
        sorted(candidates, key=lambda c: c.match_score or 0, reverse=True), start=1
    ):
        cand.rank = rank
    db.commit()
    for cand in candidates:
        db.refresh(cand)
    return candidates
