# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from pydantic import BaseModel

from app.api.deps import require_admin
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import get_db
from app.models.ai_log import AIQueryLog
from app.models.app_config import AppConfig
from app.models.place import Place
from app.models.search import Search
from app.models.user import User
from app.models.candidate import Candidate
from app.schemas.auth import AdminPasswordReset, UserOut
from app.services import criteria as criteria_service

router = APIRouter()


# --- Criteria registry (editable reference data) -------------------------------------
@router.get("/criteria")
def get_criteria(_: User = Depends(require_admin)):
    """The FULL registry (including deactivated members) for editing."""
    return criteria_service.raw()


@router.put("/criteria")
def put_criteria(body: dict, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Replace the criteria registry. Validates structure, persists, and invalidates the
    cache so edits take effect immediately."""
    nodes = body.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise HTTPException(status_code=400, detail="registry must have a non-empty 'nodes' list")
    keys = [n.get("key") for n in nodes]
    if any(not k for k in keys) or len(keys) != len(set(keys)):
        raise HTTPException(status_code=400, detail="every node needs a unique 'key'")
    keyset = set(keys)
    leaf_keys = {n["key"] for n in nodes if n.get("kind")}
    for n in nodes:
        parent = n.get("parent")
        if parent is not None and parent not in keyset:
            raise HTTPException(status_code=400, detail=f"node '{n['key']}' has unknown parent '{parent}'")
        if n.get("kind") not in (None, "objective", "computed"):
            raise HTTPException(status_code=400, detail=f"node '{n['key']}' has invalid kind")
    # Personas (if present): unique keys, and every weight key must resolve to a leaf criterion.
    personas = body.get("personas", [])
    if not isinstance(personas, list):
        raise HTTPException(status_code=400, detail="'personas' must be a list")
    pkeys = [p.get("key") for p in personas]
    if any(not k for k in pkeys) or len(pkeys) != len(set(pkeys)):
        raise HTTPException(status_code=400, detail="every persona needs a unique 'key'")
    for p in personas:
        bad = [k for k in (p.get("weights") or {}) if k not in leaf_keys]
        if bad:
            raise HTTPException(status_code=400,
                                detail=f"persona '{p['key']}' weights unknown criteria: {bad}")
        badf = [k for k in (p.get("filters") or []) if k not in leaf_keys]
        if badf:
            raise HTTPException(status_code=400,
                                detail=f"persona '{p['key']}' filters unknown criteria: {badf}")
    row = db.get(AppConfig, "criteria") or AppConfig(key="criteria")
    row.value = body
    db.add(row)
    db.commit()
    criteria_service.invalidate()
    return {"ok": True}


class PersonaSuggestRequest(BaseModel):
    prompt: str = ""


@router.post("/personas/suggest")
def suggest_personas(
    body: PersonaSuggestRequest, _: User = Depends(require_admin), db: Session = Depends(get_db),
):
    """AI-author the persona set (admin-time only). Given the criteria catalog + the admin's
    instructions, propose a list of personas (keys, labels, blurbs, match rules, weight
    profiles). Returns the proposal for review — does NOT save; the admin edits then PUTs
    /admin/criteria with personas embedded."""
    from app.services import ai_client

    leaves = [
        {"key": n["key"], "about": n.get("ai_description") or n.get("label_en") or n["key"]}
        for n in criteria_service.leaves()
    ]
    leaf_keys = [leaf["key"] for leaf in leaves]
    reason_keys = criteria_service.reasons()
    tag_keys = list(criteria_service.tags().keys())
    schema = {
        "type": "object",
        "properties": {
            "personas": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                        "label_en": {"type": "string"}, "label_fr": {"type": "string"},
                        "blurb_en": {"type": "string"}, "blurb_fr": {"type": "string"},
                        "match": {
                            "type": "object",
                            "properties": {
                                "reasons": {"type": "array", "items": {"type": "string", "enum": reason_keys}},
                                "tags": {"type": "array", "items": {"type": "string", "enum": tag_keys}},
                            },
                            "required": ["reasons", "tags"], "additionalProperties": False,
                        },
                        "weights": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "key": {"type": "string", "enum": leaf_keys},
                                    "weight": {"type": "number", "minimum": 0, "maximum": 3},
                                },
                                "required": ["key", "weight"], "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["key", "label_en", "label_fr", "blurb_en", "blurb_fr", "match", "weights"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["personas"], "additionalProperties": False,
    }
    instr = (
        "You design 'personas' (relocation archetypes) for a country-recommendation app. Each "
        "persona has a snake_case key, EN/FR label + one-line blurb, a match rule (which "
        "reasons-for-leaving and concern tags imply it), and a weight profile (importance 0-3 "
        "for ONLY the criteria that critically discriminate this archetype — omit the rest, they "
        "default to 0). Always include a 'neutral' fallback. Use only the given criteria keys.\n\n"
        f"Reasons: {', '.join(reason_keys)}\nTags: {', '.join(tag_keys)}\n"
        "Criteria (key — about):\n" + "\n".join(f"- {leaf['key']} — {leaf['about']}" for leaf in leaves)
        + f"\n\nAdmin instructions: {body.prompt or '(none — produce a sensible default set)'}"
    )
    try:
        data = ai_client.respond_json(
            instr, schema, schema_name="personas", web_search=False,
            model=settings.openai_model, kind="research", db=db, user_id=_.id,
        )
    except ai_client.AIUnavailable:
        raise HTTPException(status_code=503, detail="AI unavailable")
    # Normalise weights from the keyed array (strict-schema-friendly) to a {key: weight} map.
    out = []
    for p in data.get("personas", []):
        p = dict(p)
        p["weights"] = {w["key"]: w["weight"] for w in p.get("weights", []) if w.get("key") in set(leaf_keys)}
        p["active"] = True
        out.append(p)
    return {"personas": out}


# --- Places CRUD (deactivate, not delete) --------------------------------------------
class PlaceUpsert(BaseModel):
    name: str | None = None
    kind: str | None = None        # country / region / city
    iso_code: str | None = None
    parent_id: int | None = None
    attributes: dict | None = None
    summary_fr: str | None = None
    summary_en: str | None = None
    active: bool | None = None


@router.post("/places")
def create_place(body: PlaceUpsert, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    if not body.name or not body.kind:
        raise HTTPException(status_code=400, detail="name and kind are required")
    place = Place(kind=body.kind, name=body.name, iso_code=body.iso_code,
                  parent_id=body.parent_id, attributes=body.attributes or {},
                  summary_fr=body.summary_fr, summary_en=body.summary_en, source="admin")
    db.add(place)
    db.commit()
    db.refresh(place)
    return {"id": place.id, "name": place.name, "kind": place.kind}


@router.patch("/places/{place_id}")
def update_place(place_id: int, body: PlaceUpsert, _: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    place = db.get(Place, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(place, field, value)
    db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/reset-password", status_code=204)
def reset_password(
    user_id: int,
    body: AdminPasswordReset,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin sets a new password for any user."""
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    target.password_hash = hash_password(body.password)
    db.commit()


@router.post("/users/{user_id}/reset", status_code=204)
def reset_user(user_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Admin: wipe a user's profile + searches so they start over (keeps the account)."""
    from app.services import account

    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    account.reset_user_data(db, target)


@router.get("/users", response_model=list[UserOut])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(User).order_by(User.created_at.desc()).all()


@router.get("/searches")
def list_searches(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    """All users' searches with who owns them and how many candidates they hold."""
    rows = db.query(Search).order_by(Search.updated_at.desc()).limit(500).all()
    out = []
    for s in rows:
        active = [c for c in s.candidates if c.status == "active"]
        out.append({
            "id": s.id,
            "user_email": s.user.email if s.user else None,
            "title": s.title,
            "candidates": len(active),
            "selected": sum(1 for c in active if c.selected),
            "updated_at": s.updated_at,
        })
    return out


@router.get("/places")
def list_places(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    """The place database with data provenance & freshness, so admins can see which
    countries are still seed-only vs AI-enriched."""
    rows = db.query(Place).order_by(Place.name).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "kind": p.kind,
            "iso_code": p.iso_code,
            "source": p.source,
            "active": p.active,
            "enriched": bool(p.source == "ai" or p.facts or p.criteria_detail),
            "freshness_at": p.freshness_at,
        }
        for p in rows
    ]


@router.post("/places/{place_id}/refresh-evals")
def refresh_evals(
    place_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)
):
    """Force a fresh AI evaluation of all objective criteria for one country (admin)."""
    from app.services import criteria, criterion_eval

    place = db.get(Place, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    made = criterion_eval.populate(db, [place], criteria.objective_keys(), force=True)
    return {"ok": True, "place": place.name, "evaluated": made}


@router.get("/ai-log")
def ai_log(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.query(AIQueryLog).order_by(AIQueryLog.created_at.desc()).limit(500).all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "kind": r.kind,
            "model": r.model,
            "tokens_in": r.tokens_in,
            "tokens_out": r.tokens_out,
            "latency_ms": r.latency_ms,
            "cost_estimate": r.cost_estimate,
            "created_at": r.created_at,
        }
        for r in rows
    ]
