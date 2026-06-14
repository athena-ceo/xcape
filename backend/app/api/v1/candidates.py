# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

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
)
from app.services import ai_client, board, comparison, criteria, criterion_eval, place_research
from app.services import shortlist as shortlist_service
from app.services.shortlist import MAX_COMPARE

router = APIRouter()


def _owned(db: Session, user: User, search_id: int) -> Search:
    search = db.get(Search, search_id)
    if search is None or search.user_id != user.id:
        raise HTTPException(status_code=404, detail="Search not found")
    return search


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
    locale = profile.user.locale if (profile and profile.user) else "fr"

    for cand in candidates:
        cand.vs_current = comparison.compute_deltas(cand.per_criterion, base_attrs)
        if cand.place:
            view = board.criteria_view(db, cand.place, profile, custom_defs, locale)
            cand.quality = view["quality"]
            cand.reasons = view["reasons"]
            cand.pending = view["pending"]
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
        existing.status = "active"
        db.commit()
        db.refresh(existing)
        return existing

    # A freshly added country joins the comparison if there's still room (<= 5).
    candidate = Candidate(
        search_id=search_id,
        place_id=place.id,
        per_criterion=place.attributes or {},
        selected=_selected_count(db, search_id) < MAX_COMPARE,
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
    search_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """A PDF report of the current search: summary table + per-country details + profile."""
    from app.services import report

    search = _owned(db, user, search_id)
    pdf = report.build_report(db, user, search)
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
    if not any(c.get("key") == key for c in defs):
        defs.append({"key": key, "label": body.label, "description": body.description,
                     "weight": body.weight})
        search.custom_criteria = defs
    if key not in (search.criteria_set or []):
        search.criteria_set = [*(search.criteria_set or []), key]
    db.commit()
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
            ev = criterion_eval.evaluate(db, place, key, d["label"], d.get("description"), user_id=user.id)
            if ev is not None:
                made += 1
    if made:
        shortlist_service.rescore_candidates(db, user, search)
    return list_candidates(search_id, user=user, db=db)
