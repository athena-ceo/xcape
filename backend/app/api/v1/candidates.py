# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.candidate import Candidate
from app.models.place import Place
from app.models.search import Search
from app.models.user import User
from app.schemas.search import (
    AddCandidateRequest,
    AddCriterionRequest,
    AddCustomCriterionRequest,
    CandidateOut,
    SetSelectedRequest,
    SuggestCriteriaRequest,
    UpdateCustomCriterionRequest,
)
from app.services import (
    ai_client, board, comparison, criteria, criteria_select, criterion_eval,
    custom_criteria, place_research,
)
from app.models.profile import Profile
from app.services import shortlist as shortlist_service
from app.services.shortlist import MAX_COMPARE

router = APIRouter()


def _owned(db: Session, user: User, search_id: int) -> Search:
    search = db.get(Search, search_id)
    if search is None or search.user_id != user.id:
        raise HTTPException(status_code=404, detail="Search not found")
    return search


def _board_violates_filters(db: Session, user: User, search: Search) -> bool:
    """True if any currently-SELECTED country violates an active hard filter — meaning the
    stored board is stale w.r.t. the filters and should be re-ranked (filters are exclusionary).

    Pinned countries (override == "in") are skipped: the user accepted that violation on
    purpose, so it must not trigger a self-heal that would otherwise churn the board on
    every load."""
    profile = user.profile
    if not (profile and profile.filters):
        return False
    selected = (
        db.query(Candidate)
        .filter(Candidate.search_id == search.id, Candidate.status == "active",
                Candidate.selected.is_(True))
        .all()
    )
    selected = [c for c in selected if c.override != "in"]  # pinned violations are intentional
    if not selected:
        return False
    custom_defs = list(search.custom_criteria or [])
    eval_keys = criteria.objective_keys() + [c["key"] for c in custom_defs if c.get("key")]
    evals = criterion_eval.values_for_places(db, [c.place_id for c in selected], eval_keys)
    return any(
        c.place and shortlist_service.filter_status(
            c.place, profile, evals.get(c.place_id), custom_defs
        )["violations"]
        for c in selected
    )


def _selected_count(db: Session, search_id: int, exclude_id: int | None = None) -> int:
    q = db.query(Candidate).filter(
        Candidate.search_id == search_id,
        Candidate.status == "active",
        Candidate.selected.is_(True),
    )
    if exclude_id is not None:
        q = q.filter(Candidate.id != exclude_id)
    return q.count()


@router.get("/{search_id}/candidates", response_model=list[CandidateOut])
def list_candidates(
    search_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    search = _owned(db, user, search_id)
    custom_criteria.merge_into_search(db, user, search)  # self-heal: bring in persistent customs
    # Self-heal: hard filters are exclusionary, so if the stored board still holds countries
    # that violate the current filters (set before this load), re-rank to drop them. Keeps a
    # plain page load consistent without requiring an explicit Repopulate.
    if _board_violates_filters(db, user, search):
        shortlist_service.repopulate_board(db, user, search)
    candidates = (
        db.query(Candidate)
        .filter(Candidate.search_id == search_id, Candidate.status == "active")
        .order_by(Candidate.match_score.desc().nullslast())
        .all()
    )
    # Annotate each candidate with how it compares to the user's current country
    # (fast path: baseline must already be in the DB; France is seeded).
    baseline = comparison.get_current_country_place(db, user, research=False)
    base_attrs = baseline.attributes if baseline else None

    # Language is judged by whether the user can communicate (their known languages),
    # so the arrow stays consistent with the displayed languages.
    profile = user.profile
    known = {
        str(lang).lower()
        for lang in ((profile.language_skills or {}).get("known") or [] if profile else [])
    }
    base_langs = {str(lang).lower() for lang in ((base_attrs or {}).get("languages") or [])}

    custom_defs = search.custom_criteria or []
    # Cached evals (objective built-ins + custom) drive the live hard-filter check below.
    eval_keys = criteria.objective_keys() + [c["key"] for c in custom_defs if c.get("key")]

    for cand in candidates:
        cand.vs_current = comparison.compute_deltas(cand.per_criterion, base_attrs)
        if cand.place:
            view = board.criteria_view(db, cand.place, profile, custom_defs)
            cand.quality = view["quality"]
            cand.reasons = view["reasons"]
            cand.pending = view["pending"]
            evals = criterion_eval.values_for_place(db, cand.place_id, eval_keys)
            cand.filter_violations = shortlist_service.filter_status(
                cand.place, profile, evals, custom_defs
            )["violations"]
        if known:
            # Read languages from the live place so existing searches benefit without
            # needing the shortlist rebuilt.
            place_attrs = cand.place.attributes if cand.place else (cand.per_criterion or {})
            cand_langs = {str(lang).lower() for lang in (place_attrs.get("languages") or [])}
            cand_ok, base_ok = bool(known & cand_langs), bool(known & base_langs)
            cand.vs_current["language_ease"] = (
                "same" if cand_ok == base_ok else ("better" if cand_ok else "worse")
            )
    return candidates


@router.get("/{search_id}/filter-advice")
def filter_advice(
    search_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """How the active hard filters constrain the pool: how many countries qualify and which
    single filter to relax (highest-scoring otherwise-excluded country first)."""
    search = _owned(db, user, search_id)
    return shortlist_service.filter_advice(db, user, search)


@router.post("/{search_id}/candidates", response_model=CandidateOut, status_code=201)
def add_candidate(
    search_id: int,
    body: AddCandidateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    search = _owned(db, user, search_id)
    place: Place | None = None
    if body.place_id is not None:
        place = db.get(Place, body.place_id)
    elif body.place_name:
        place = db.query(Place).filter(Place.name.ilike(body.place_name)).first()
        if place is None:
            # Not in the built-in DB — research it on demand and cache it.
            try:
                place = place_research.research_place(db, body.place_name, user_id=user.id)
            except ai_client.AIUnavailable:
                raise HTTPException(
                    status_code=503, detail="AI research unavailable (no API key configured)"
                )
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")

    existing = (
        db.query(Candidate)
        .filter(Candidate.search_id == search_id, Candidate.place_id == place.id)
        .first()
    )
    if existing:
        # Explicit add is a user override: pin it on the board even if it violates a hard
        # filter, and un-banish it if it had been excluded.
        existing.status = "active"
        existing.override = "in"
        if not existing.selected and _selected_count(db, search_id, exclude_id=existing.id) < MAX_COMPARE:
            existing.selected = True
        db.commit()
        shortlist_service.rescore_candidates(db, user, search)
        db.refresh(existing)
        return existing

    # A freshly added country joins the comparison if there's still room (<= 5). It's pinned
    # ("in") so the user's explicit choice survives filters, self-heal and repopulate.
    candidate = Candidate(
        search_id=search_id,
        place_id=place.id,
        per_criterion=place.attributes or {},
        selected=_selected_count(db, search_id) < MAX_COMPARE,
        override="in",
    )
    db.add(candidate)
    db.commit()
    # Score now from whatever evals/buckets exist; missing cells fill in progressively via
    # /evaluate-pending (optimistic UI) rather than blocking this request on AI calls.
    shortlist_service.rescore_candidates(db, user, search)
    db.refresh(candidate)
    return candidate


@router.get("/{search_id}/candidates/{candidate_id}/explanation")
def explain(
    search_id: int,
    candidate_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """How this candidate's score was derived (per-criterion value × weight)."""
    _owned(db, user, search_id)
    candidate = db.get(Candidate, candidate_id)
    if candidate is None or candidate.search_id != search_id:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return shortlist_service.explain_candidate(db, user, candidate)


@router.patch("/{search_id}/candidates/{candidate_id}", response_model=CandidateOut)
def set_selected(
    search_id: int,
    candidate_id: int,
    body: SetSelectedRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Select / unselect a candidate for the comparison board (server enforces max 5)."""
    _owned(db, user, search_id)
    candidate = db.get(Candidate, candidate_id)
    if candidate is None or candidate.search_id != search_id:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if body.selected and not candidate.selected:
        if _selected_count(db, search_id, exclude_id=candidate_id) >= MAX_COMPARE:
            raise HTTPException(
                status_code=409, detail=f"At most {MAX_COMPARE} countries can be compared"
            )
    candidate.selected = body.selected
    db.commit()
    db.refresh(candidate)
    return candidate


@router.post("/{search_id}/candidates/{candidate_id}/exclude", response_model=CandidateOut)
def exclude_candidate(
    search_id: int,
    candidate_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Explicitly banish a country: it leaves the board and never re-enters via score/filters
    (override == "out"). Its row is kept so it shows in the "excluded" bar for restore."""
    _owned(db, user, search_id)
    candidate = db.get(Candidate, candidate_id)
    if candidate is None or candidate.search_id != search_id:
        raise HTTPException(status_code=404, detail="Candidate not found")
    candidate.override = "out"
    candidate.selected = False
    db.commit()
    db.refresh(candidate)
    return candidate


@router.post("/{search_id}/candidates/{candidate_id}/restore", response_model=CandidateOut)
def restore_candidate(
    search_id: int,
    candidate_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Clear an explicit override (pin or exclusion): the country returns to the neutral pool,
    re-ranked by filters + score. It does NOT auto-join the board — the user re-adds it."""
    _owned(db, user, search_id)
    candidate = db.get(Candidate, candidate_id)
    if candidate is None or candidate.search_id != search_id:
        raise HTTPException(status_code=404, detail="Candidate not found")
    candidate.override = None
    candidate.selected = False
    db.commit()
    db.refresh(candidate)
    return candidate


@router.delete("/{search_id}/candidates/{candidate_id}", status_code=204)
def remove_candidate(
    search_id: int,
    candidate_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _owned(db, user, search_id)
    candidate = db.get(Candidate, candidate_id)
    if candidate is None or candidate.search_id != search_id:
        raise HTTPException(status_code=404, detail="Candidate not found")
    candidate.status = "removed"
    db.commit()


@router.post("/{search_id}/criteria", response_model=list[CandidateOut])
def add_criterion(
    search_id: int,
    body: AddCriterionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a built-in criterion column to the search. Objective criteria with no seed value
    are filled progressively via /evaluate-pending (optimistic UI), not synchronously here."""
    search = _owned(db, user, search_id)
    if body.key not in (search.criteria_set or []):
        search.criteria_set = [*(search.criteria_set or []), body.key]
        db.commit()
    return list_candidates(search_id, user=user, db=db)


@router.get("/{search_id}/report.pdf")
def report_pdf(
    search_id: int, lang: str | None = None,
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """A PDF report of the current search: summary table + per-country details + profile.

    `lang` (optional) overrides the language so the report matches the UI the user is
    viewing, even if their stored locale differs."""
    from app.services import report

    search = _owned(db, user, search_id)
    pdf = report.build_report(db, user, search, lang=lang)
    name = f"xcape-report-{search_id}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/{search_id}/custom-criteria")
def list_custom_criteria(
    search_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """The search's user-defined criteria: [{key, label, description, weight}]."""
    search = _owned(db, user, search_id)
    return search.custom_criteria or []


@router.post("/{search_id}/custom-criteria", response_model=list[CandidateOut])
def add_custom_criterion(
    search_id: int,
    body: AddCustomCriterionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Register a user-defined criterion. Returns immediately with the column showing as
    pending; the per-country evaluations fill in progressively via /evaluate-pending
    (optimistic UI — no long blocking wait)."""
    search = _owned(db, user, search_id)
    key = criterion_eval.slugify(body.label)
    defs = list(search.custom_criteria or [])
    new_def = {"key": key, "label": body.label, "description": body.description, "weight": body.weight}
    if not any(c.get("key") == key for c in defs):
        defs.append(new_def)
        search.custom_criteria = defs
    if key not in (search.criteria_set or []):
        search.criteria_set = [*(search.criteria_set or []), key]
    db.commit()
    custom_criteria.persist_to_profile(db, user, [new_def])  # follow the user across searches
    return list_candidates(search_id, user=user, db=db)


@router.patch("/{search_id}/custom-criteria/{key}", response_model=list[CandidateOut])
def update_custom_criterion(
    search_id: int,
    key: str,
    body: UpdateCustomCriterionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a custom criterion's importance (weight) and/or its hard-filter minimum
    (min, 0-1; null clears it), then repopulate so the change takes effect."""
    search = _owned(db, user, search_id)
    # Deep-copy the defs: mutating the ORM's loaded dicts in place would leave old == new,
    # so SQLAlchemy would emit no UPDATE for this JSON column (the edit would silently
    # revert). flag_modified additionally forces the column dirty to be safe.
    defs = [dict(c) for c in (search.custom_criteria or [])]
    target = next((c for c in defs if c.get("key") == key), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Custom criterion not found")
    fields = body.model_dump(exclude_unset=True)
    if "weight" in fields and fields["weight"] is not None:
        target["weight"] = float(fields["weight"])
    if "min" in fields:
        if fields["min"] in (None, ""):
            target.pop("min", None)
        else:
            target["min"] = float(fields["min"])
    search.custom_criteria = defs
    flag_modified(search, "custom_criteria")
    db.commit()
    # Mirror the weight/min edit onto the persisted copy (so it sticks across searches).
    prof = user.profile
    if prof and prof.custom_criteria:
        pc = [dict(c) for c in prof.custom_criteria]
        for c in pc:
            if c.get("key") == key:
                if "weight" in target:
                    c["weight"] = target["weight"]
                if "min" in target:
                    c["min"] = target["min"]
                else:
                    c.pop("min", None)
        prof.custom_criteria = pc
        flag_modified(prof, "custom_criteria")
        db.commit()
    shortlist_service.repopulate_board(db, user, search)
    return list_candidates(search_id, user=user, db=db)


@router.post("/{search_id}/apply-persona", response_model=list[CandidateOut])
def apply_persona(
    search_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Add the user's persona's specific criteria to this search (e.g. asset-tax & banking for
    asset_protection; pension-visa for retiree; per-community tolerance for safety_community,
    expanded once per community the user flagged). Cache-first; they then evaluate via
    /evaluate-pending like any custom criterion."""
    search = _owned(db, user, search_id)
    prof = user.profile
    persona = criteria.persona(getattr(prof, "persona", None))
    if persona is None:
        return list_candidates(search_id, user=user, db=db)

    locale = user.locale or "fr"
    defs = list(search.custom_criteria or [])
    have = {c.get("key") for c in defs}
    comms = {c["key"]: c for c in criteria.communities()}
    user_comms = (prof.minority_groups or []) if prof else []
    added: list[str] = []

    def _add(label: str, description: str, weight: float, category: str | None):
        key = criterion_eval.slugify(label)
        if not key or key in have:
            return
        d = {"key": key, "label": label, "description": description, "weight": weight,
             "source": "persona"}  # per-search (regenerated); not persisted to the profile
        if category:
            d["category"] = category  # file it under a built-in category, not "Your criteria"
        defs.append(d)
        have.add(key)
        added.append(key)

    for cc in persona.get("custom_criteria", []):
        base = cc.get(f"label_{locale}") or cc.get("label_en") or cc.get("label") or "criterion"
        desc = cc.get("description", "")
        category = cc.get("category")
        if cc.get("per_community"):
            for ck in user_comms:
                c = comms.get(ck)
                clabel = (c.get(f"label_{locale}") or c.get("label_en") or ck) if c else ck
                _add(f"{base} — {clabel}", desc.replace("{community}", clabel), 2.0, category)
        else:
            _add(base, desc, 1.5, category)

    if added:
        search.custom_criteria = defs
        search.criteria_set = list({*(search.criteria_set or []), *added})
        db.commit()
        shortlist_service.rescore_candidates(db, user, search)
    return list_candidates(search_id, user=user, db=db)


@router.post("/{search_id}/suggest-criteria", response_model=list[CandidateOut])
def suggest_criteria(
    search_id: int,
    body: SuggestCriteriaRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """From the user's chosen tags + free-text situation, AI-select which criteria matter:
    set their importance weights and add any proposed custom criteria, then re-rank."""
    search = _owned(db, user, search_id)
    result = criteria_select.suggest(db, user, tags=body.tags, free_text=body.text or "")

    # Apply weights to the profile (merge with any existing).
    if result["weights"]:
        profile = user.profile or Profile(user_id=user.id)
        if profile.id is None:
            db.add(profile)
        profile.criteria_weights = {**(profile.criteria_weights or {}), **result["weights"]}
        db.commit()

    # Register suggested custom criteria (evaluated progressively via /evaluate-pending).
    defs = list(search.custom_criteria or [])
    keys = {c.get("key") for c in defs}
    added: list[dict] = []
    for c in result["custom"]:
        key = criterion_eval.slugify(c["label"])
        if key in keys:
            continue
        d = {"key": key, "label": c["label"], "description": c.get("description"), "weight": 1.0}
        defs.append(d)
        added.append(d)
        keys.add(key)
        if key not in (search.criteria_set or []):
            search.criteria_set = [*(search.criteria_set or []), key]
    search.custom_criteria = defs
    db.commit()
    custom_criteria.persist_to_profile(db, user, added)  # the user's own words → persist for them

    shortlist_service.rescore_candidates(db, user, search)
    return list_candidates(search_id, user=user, db=db)


@router.post("/{search_id}/evaluate-pending", response_model=list[CandidateOut])
def evaluate_pending(
    search_id: int,
    limit: int = 4,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Evaluate up to `limit` not-yet-cached (country × criterion) cells for this search's
    board, then re-rank and return the candidates. The frontend calls this repeatedly until
    nothing is pending, so cells fill in with a visible animation instead of one long wait."""
    search = _owned(db, user, search_id)
    # One definition map for built-in + custom criteria — evaluated through one path.
    defs = criteria.definitions(search.custom_criteria or [])
    eval_keys = list(defs.keys())
    # Only spend AI on criteria the user actually weights (> 0) — same gate board.criteria_view
    # uses to mark cells pending, so the progressive drain doesn't loop on ignored criteria.
    eff = shortlist_service._effective_weights(user.profile)
    custom_w = {c["key"]: float(c.get("weight", 1.0)) for c in (search.custom_criteria or []) if c.get("key")}
    weight_of = {**eff, **custom_w}

    # Selected (on-board) candidates first, then the rest; the baseline (current country)
    # last so its cells fill too — no blanks in any column.
    cands = (
        db.query(Candidate)
        .filter(Candidate.search_id == search_id, Candidate.status == "active")
        .order_by(Candidate.selected.desc())
        .all()
    )
    places = [c.place for c in cands if c.place]
    base = comparison.get_current_country_place(db, user, research=False)
    if base is not None and base.id not in {p.id for p in places}:
        places.append(base)

    made = 0
    for place in places:
        if made >= limit:
            break
        have = set(criterion_eval.evals_for_place(db, place.id, eval_keys).keys())
        attrs = place.attributes or {}
        for key, d in defs.items():
            if made >= limit:
                break
            if key in have or attrs.get(key):
                continue  # already evaluated, or has a usable seed bucket — no AI call
            if weight_of.get(key, 0) <= 0:
                continue  # unimportant to this user — don't spend an AI call on it
            ev = criterion_eval.evaluate(db, place, key, d["label"], d.get("description"), user_id=user.id)
            if ev is not None:
                made += 1
    if made:
        shortlist_service.rescore_candidates(db, user, search)
    return list_candidates(search_id, user=user, db=db)
