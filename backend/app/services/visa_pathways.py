# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Visa / right-to-settle pathway catalog — (destination × category), on-demand.

Visa is the gate: a destination is only reachable if some immigration *category* (work,
retirement, investment, …) offers this person a viable route. A pathway's rules are largely
nationality-independent (the program's own thresholds and timelines), so — like the objective
criterion evals — we cache them per `(place, category)` in `place_custom_evals` under
`key = "visa_<category>"`, with the structured terms in `meta` (difficulty, income/investment
thresholds, residency→PR→citizenship timeline, key requirements). Origin-neutral on purpose:
this is a SHARED cross-user cache; any per-citizenship eligibility is applied as a deterministic
overlay at read time (see `shortlist`), never baked into the cached row.

Evaluated **on-demand** — only the categories relevant to a given user, when they open a place —
to bound cost (no bulk 217×categories run). Reuses the criterion_eval versioning / freshness.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.custom_eval import PlaceCustomEval
from app.models.place import Place
from app.models.profile import Profile
from app.services import ai_client
from app.services.criterion_eval import _fresh, level_from_score

# Bump when the pathway prompt/schema below changes in a way that should invalidate cached
# pathway rows (independent of the criterion-eval version).
VISA_PROMPT_VERSION = "1"

# Catalog categories — destination PROGRAMS (free movement is citizenship-based, handled by the
# overlay in shortlist, so it is NOT part of the on-demand catalog). Order = display order.
CATEGORY_LABELS: dict[str, dict[str, str]] = {
    "work": {"en": "Work / skilled employment", "fr": "Travail / emploi qualifié"},
    "retirement": {"en": "Retirement / passive income", "fr": "Retraite / revenus passifs"},
    "investment": {"en": "Investment (golden / real-estate / business)",
                   "fr": "Investissement (golden / immobilier / entreprise)"},
    "entrepreneur": {"en": "Entrepreneur / startup", "fr": "Entrepreneur / startup"},
    "digital_nomad": {"en": "Digital nomad / remote work", "fr": "Nomade numérique / télétravail"},
    "ancestry": {"en": "Ancestry / descent", "fr": "Ascendance / filiation"},
    "family": {"en": "Family / spouse reunification", "fr": "Famille / regroupement familial"},
    "student": {"en": "Student", "fr": "Étudiant"},
}
CATALOG_CATEGORIES = list(CATEGORY_LABELS.keys())

# Which categories are worth surfacing for a given persona (in addition to the universal ones
# and any user-declared ancestry). Personas not listed get only the universal set.
PERSONA_CATEGORIES: dict[str, list[str]] = {
    "retiree": ["retirement"],
    "professional": ["work"],
    "asset_protection": ["investment"],
    "entrepreneur": ["entrepreneur", "investment"],
    "family": ["family"],
    "climate_lifestyle": ["digital_nomad", "retirement"],
    "broaden_horizons": ["digital_nomad", "student"],
}
# Categories nearly everyone could plausibly use.
UNIVERSAL_CATEGORIES = ["work", "family"]


def category_label(category: str, lang: str = "en") -> str:
    d = CATEGORY_LABELS.get(category, {})
    return d.get(lang) or d.get("en") or category


def _key(category: str) -> str:
    return f"visa_{category}"


def _label(category: str) -> str:
    return CATEGORY_LABELS.get(category, {}).get("en", category)


def _fp(category: str) -> str:
    """Fingerprint for a pathway cell — the invariant part of the prompt (place excluded)."""
    raw = f"{VISA_PROMPT_VERSION}\x1fvisa\x1f{category}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def relevant_categories(profile: Profile | None, place: Place | None) -> list[str]:
    """The pathway categories worth showing this user for this place: their persona's set, any
    declared ancestry tie to THIS place, plus the universal routes — ordered, deduped."""
    cats: list[str] = []
    persona = getattr(profile, "persona", None) if profile else None
    cats += PERSONA_CATEGORIES.get(persona or "", [])
    iso = (place.iso_code or "").upper() if place else ""
    anc = set()
    if profile and profile.user and getattr(profile.user, "ancestry_countries", None):
        anc = {str(c).upper() for c in profile.user.ancestry_countries}
    if iso and iso in anc:
        cats.append("ancestry")
    cats += UNIVERSAL_CATEGORIES
    seen: set[str] = set()
    out: list[str] = []
    for c in cats:
        if c in CATALOG_CATEGORIES and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _schema() -> dict:
    nullable_int = {"type": ["integer", "null"]}
    nullable_num = {"type": ["number", "null"]}
    return {
        "type": "object",
        "properties": {
            "exists": {"type": "boolean"},  # does this route to legal residence exist at all?
            "difficulty": {"type": "integer", "minimum": 0, "maximum": 100},  # 100 = very easy
            "income_eur": nullable_int,       # min qualifying income/pension per YEAR, €
            "investment_eur": nullable_int,   # min qualifying investment / capital, €
            "pr_years": nullable_num,         # years of residence → permanent residence
            "citizenship_years": nullable_num,  # years of residence → naturalisation
            "requirements": {"type": "array", "items": {"type": "string"}},
            "summary_fr": {"type": "string"},
            "summary_en": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["exists", "difficulty", "income_eur", "investment_eur", "pr_years",
                     "citizenship_years", "requirements", "summary_fr", "summary_en", "sources"],
        "additionalProperties": False,
    }


def evaluate_pathway(
    db: Session, place: Place, category: str, *,
    force: bool = False, stale_days: int = 0, user_id: int | None = None,
) -> PlaceCustomEval | None:
    """Assess one (place, category) pathway (cache-first). Returns the row, or None if AI is off."""
    if category not in CATALOG_CATEGORIES:
        return None
    key = _key(category)
    existing = (
        db.query(PlaceCustomEval)
        .filter(PlaceCustomEval.place_id == place.id, PlaceCustomEval.key == key)
        .first()
    )
    fp = _fp(category)
    if existing and not force and _fresh(existing, fp, stale_days):
        return existing

    label = _label(category)
    prompt = (
        f'Describe the "{label}" immigration / right-to-residence pathway to {place.name} for a '
        f"prospective foreign resident. Judge the PROGRAM'S OWN RULES, independent of any "
        f"particular nationality (do not assume a specific citizenship or home country). Report:\n"
        f"- exists: whether {place.name} offers a recognised {label} route to legal residence.\n"
        f"- difficulty: 0-100 where 100 = very easy / highly accessible and 0 = effectively "
        f"impossible — reflect realistic approval odds, cost, quotas, processing burden and "
        f"official discretion. If no such route exists, difficulty 0.\n"
        f"- income_eur: minimum qualifying income or pension PER YEAR in euros if the route sets "
        f"an income threshold, else null.\n"
        f"- investment_eur: minimum qualifying investment or capital in euros if applicable, "
        f"else null.\n"
        f"- pr_years: typical years of continuous residence to reach permanent residence, else "
        f"null. citizenship_years: typical years of residence to be eligible for naturalisation, "
        f"else null.\n"
        f"- requirements: 3-6 short bullet strings of the key conditions (e.g. job offer, "
        f"language level, clean criminal record, private health insurance, minimum stay).\n"
        f"Add a concrete 1-2 sentence summary in French (summary_fr) and English (summary_en), "
        f"written as a neutral, friendly advisor stating the facts — in the THIRD PERSON, never "
        f"first or second person (no \"I\", \"we\", \"you\"). Name the actual program if it has "
        f"one, and do NOT restate the difficulty number. Put sources ONLY in the sources array as "
        f"bare https URLs. Use web search and favour the most recent data (2025–2026)."
    )
    try:
        data = ai_client.respond_json(
            prompt, _schema(), schema_name="visa_pathway", web_search=True,
            model=settings.openai_chat_model, kind="custom", db=db, user_id=user_id,
        )
    except ai_client.AIUnavailable:
        return None

    exists = bool(data.get("exists"))
    difficulty = int(data.get("difficulty") or 0)
    if not exists:
        difficulty = 0
    meta = {
        "category": category,
        "exists": exists,
        "difficulty": difficulty,
        "income_eur": data.get("income_eur"),
        "investment_eur": data.get("investment_eur"),
        "pr_years": data.get("pr_years"),
        "citizenship_years": data.get("citizenship_years"),
        "requirements": data.get("requirements") or [],
    }
    fields = dict(
        label=label, score=difficulty, level=level_from_score(difficulty),
        summary_fr=data.get("summary_fr"), summary_en=data.get("summary_en"),
        sources=data.get("sources", []), meta=meta, prompt_fp=fp,
        freshness_at=datetime.now(timezone.utc),
    )
    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
        db.commit()
        db.refresh(existing)
        return existing
    ev = PlaceCustomEval(place_id=place.id, key=key, **fields)
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def cached_rows(db: Session, place_id: int) -> dict[str, PlaceCustomEval]:
    """All cached pathway rows for a place, keyed by category (no AI)."""
    keys = [_key(c) for c in CATALOG_CATEGORIES]
    rows = (
        db.query(PlaceCustomEval)
        .filter(PlaceCustomEval.place_id == place_id, PlaceCustomEval.key.in_(keys))
        .all()
    )
    return {str((r.meta or {}).get("category") or r.key.removeprefix("visa_")): r for r in rows}


def ensure_for_place(
    db: Session, place: Place, categories: list[str], *,
    stale_days: int = 0, user_id: int | None = None,
) -> dict[str, PlaceCustomEval]:
    """Return {category: pathway row} for the requested categories, evaluating any that are
    missing or stale on-demand (cache-first). Categories outside the catalog are ignored."""
    out: dict[str, PlaceCustomEval] = {}
    for c in categories:
        ev = evaluate_pathway(db, place, c, stale_days=stale_days, user_id=user_id)
        if ev is not None:
            out[c] = ev
    return out


def pathway_payload(ev: PlaceCustomEval, lang: str = "en") -> dict:
    """Serialise a pathway row for the API / drill-down panel (both languages carried)."""
    m = ev.meta or {}
    return {
        "category": m.get("category"),
        "exists": m.get("exists", True),
        "difficulty": ev.score,
        "income_eur": m.get("income_eur"),
        "investment_eur": m.get("investment_eur"),
        "pr_years": m.get("pr_years"),
        "citizenship_years": m.get("citizenship_years"),
        "requirements": m.get("requirements") or [],
        "summary_fr": ev.summary_fr or "",
        "summary_en": ev.summary_en or "",
        "sources": ev.sources or [],
    }
