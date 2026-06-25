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
VISA_PROMPT_VERSION = "3"  # v3: + program_name and min_stay_days (physical-presence requirement)

# Per-category version — bump ONE category to invalidate only its cached rows (instead of churning
# every visa pathway via VISA_PROMPT_VERSION). Appended to the fingerprint only when set, so other
# categories keep a byte-identical fingerprint. ancestry v2: prompt now covers descent + return laws.
CATEGORY_VERSION: dict[str, str] = {"ancestry": "2"}

# Catalog categories — destination PROGRAMS (free movement is citizenship-based, handled by the
# overlay in shortlist, so it is NOT part of the on-demand catalog). Order = display order.
CATEGORY_LABELS: dict[str, dict[str, str]] = {
    "work": {"en": "Work / skilled employment", "fr": "Travail / emploi qualifié"},
    "retirement": {"en": "Retirement / passive income", "fr": "Retraite / revenus passifs"},
    "investment": {"en": "Investment (golden / real-estate / business)",
                   "fr": "Investissement (golden / immobilier / entreprise)"},
    "entrepreneur": {"en": "Entrepreneur / startup", "fr": "Entrepreneur / startup"},
    "digital_nomad": {"en": "Digital nomad / remote work", "fr": "Nomade numérique / télétravail"},
    "ancestry": {"en": "Ancestry / heritage", "fr": "Ascendance / patrimoine"},
    "family": {"en": "Family / spouse reunification", "fr": "Famille / regroupement familial"},
    "student": {"en": "Student", "fr": "Étudiant"},
}
CATALOG_CATEGORIES = list(CATEGORY_LABELS.keys())

# Ethno-religious heritage → countries whose RIGHT-OF-RETURN law may apply, independent of a
# country of ancestry. Drives surfacing of the ancestry/heritage pathway for those countries
# (the AI eval describes the actual, possibly restricted, conditions — some Sephardic routes
# have closed/tightened). Keys match User.heritages.
HERITAGE_COUNTRIES: dict[str, list[str]] = {
    "jewish": ["IL", "DE", "ES", "PT"],  # Israel Law of Return; Germany Art.116; Sephardic (ES/PT)
}
# The subset strong/open enough to also boost the visa ease SCORE (not just surface the panel) —
# kept conservative so restricted routes don't inflate the ranking.
HERITAGE_VISA_BOOST: dict[str, list[str]] = {
    "jewish": ["IL"],  # Israel's Law of Return is a fast, near-automatic citizenship route
}


def heritage_countries(heritages: list | None) -> set[str]:
    """ISO codes whose heritage right-of-return pathway is worth surfacing for these heritages."""
    out: set[str] = set()
    for h in heritages or []:
        out |= {c.upper() for c in HERITAGE_COUNTRIES.get(str(h), [])}
    return out


def heritage_visa_boost_countries(heritages: list | None) -> set[str]:
    """ISO codes where a heritage tie is strong enough to max out the visa-ease score."""
    out: set[str] = set()
    for h in heritages or []:
        out |= {c.upper() for c in HERITAGE_VISA_BOOST.get(str(h), [])}
    return out

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
    cv = CATEGORY_VERSION.get(category)
    if cv:  # append only when set, so other categories' fingerprints are unchanged
        raw += f"\x1f{cv}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def relevant_categories(profile: Profile | None, place: Place | None) -> list[str]:
    """The pathway categories worth showing this user for this place: their persona's set, any
    declared ancestry tie to THIS place, plus the universal routes — ordered, deduped."""
    cats: list[str] = []
    persona = getattr(profile, "persona", None) if profile else None
    cats += PERSONA_CATEGORIES.get(persona or "", [])
    iso = (place.iso_code or "").upper() if place else ""
    anc = set()
    her: set[str] = set()
    if profile and profile.user:
        if getattr(profile.user, "ancestry_countries", None):
            anc = {str(c).upper() for c in profile.user.ancestry_countries}
        her = heritage_countries(getattr(profile.user, "heritages", None))
    # Surface the ancestry/heritage route for a declared country of ancestry OR an ethno-religious
    # heritage with a right-of-return law to THIS place (e.g. Jewish heritage → Israel).
    if iso and (iso in anc or iso in her):
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
            "min_stay_days": nullable_int,    # min days/yr of physical presence to KEEP the permit
            "program_name": {"type": ["string", "null"]},  # official program/visa name, if any
            "requirements_fr": {"type": "array", "items": {"type": "string"}},  # bullets, FR
            "requirements_en": {"type": "array", "items": {"type": "string"}},  # bullets, EN
            "summary_fr": {"type": "string"},
            "summary_en": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["exists", "difficulty", "income_eur", "investment_eur", "pr_years",
                     "citizenship_years", "min_stay_days", "program_name",
                     "requirements_fr", "requirements_en",
                     "summary_fr", "summary_en", "sources"],
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
        f"- min_stay_days: the minimum days of PHYSICAL PRESENCE per year required to KEEP this "
        f"residence permit valid (0 if there is effectively no minimum-stay requirement; null "
        f"only if genuinely unknown). This is the 'do I actually have to live there' figure.\n"
        f"- program_name: the official name of the specific program / visa if it has a recognised "
        f"one (e.g. \"D7\", \"Pensionado\", \"Golden Visa\"), else null. Do not invent a name.\n"
        f"- requirements_fr and requirements_en: the SAME 3-6 short bullet strings of the key "
        f"conditions (e.g. job offer, language level, clean criminal record, private health "
        f"insurance, minimum stay), written in French (requirements_fr) and English "
        f"(requirements_en) respectively — same bullets, same order, just translated.\n"
        f"Add a concrete 1-2 sentence summary in French (summary_fr) and English (summary_en), "
        f"written as a neutral, friendly advisor — do NOT write in the first person (no \"I\", "
        f"\"we\", \"my\", \"our\"). Name the actual program if it has one, and do NOT restate the "
        f"difficulty number. Put sources ONLY in the sources array as bare https URLs. Use web "
        f"search and favour the most recent data (2025–2026)."
        + (
            f" For this ANCESTRY / HERITAGE route, cover BOTH forms where they exist: (a) "
            f"citizenship/residence by DESCENT or lineage (e.g. jus sanguinis, a qualifying "
            f"parent/grandparent/great-grandparent, foreign-births registration) — state the "
            f"furthest eligible generation and the documentation/proof of lineage needed; and "
            f"(b) any ethno-religious or historic RIGHT OF RETURN (e.g. Israel's Law of Return "
            f"for people of Jewish heritage, Germany's Art.116(2) restoration for descendants of "
            f"those persecuted 1933–1945, Sephardic-origin routes) — say clearly WHO qualifies and "
            f"whether the route is currently OPEN, restricted, or CLOSED, and as of when. If no "
            f"descent or return route exists, set exists=false. Put the key eligibility conditions "
            f"in the requirements bullets."
            if category == "ancestry" else ""
        )
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
        "min_stay_days": data.get("min_stay_days"),
        "program_name": (data.get("program_name") or None),
        "requirements_fr": data.get("requirements_fr") or [],
        "requirements_en": data.get("requirements_en") or [],
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
    stale_days: int = 0, force: bool = False, user_id: int | None = None,
) -> dict[str, PlaceCustomEval]:
    """Return {category: pathway row} for the requested categories, evaluating any that are
    missing or stale on-demand (cache-first). With `force`, every requested category is
    re-evaluated regardless of cache. Categories outside the catalog are ignored."""
    out: dict[str, PlaceCustomEval] = {}
    for c in categories:
        ev = evaluate_pathway(db, place, c, force=force, stale_days=stale_days, user_id=user_id)
        if ev is not None:
            out[c] = ev
    return out


def pathway_payload(
    ev: PlaceCustomEval, lang: str = "en", *, rate: float = 1.0, currency: str = "EUR",
) -> dict:
    """Serialise a pathway row for the API / drill-down panel (both languages carried). The
    canonical EUR income/investment thresholds are converted to `currency` for display."""
    m = ev.meta or {}
    income_eur = m.get("income_eur")
    investment_eur = m.get("investment_eur")
    # Bilingual bullets (legacy rows carried a single `requirements` list — fall back to it).
    requirements = (m.get(f"requirements_{lang}") or m.get("requirements_en")
                    or m.get("requirements_fr") or m.get("requirements") or [])
    return {
        "category": m.get("category"),
        "exists": m.get("exists", True),
        "difficulty": ev.score,
        "currency": currency,
        "income": round(income_eur * rate) if income_eur is not None else None,
        "investment": round(investment_eur * rate) if investment_eur is not None else None,
        "pr_years": m.get("pr_years"),
        "citizenship_years": m.get("citizenship_years"),
        "min_stay_days": m.get("min_stay_days"),
        "program_name": m.get("program_name"),
        "requirements": requirements,
        "requirements_fr": m.get("requirements_fr") or m.get("requirements") or [],
        "requirements_en": m.get("requirements_en") or m.get("requirements") or [],
        "summary_fr": ev.summary_fr or "",
        "summary_en": ev.summary_en or "",
        "sources": ev.sources or [],
    }


# --- Golden-visa finder ---------------------------------------------------------------
# The finder ranks DESTINATIONS by an amount the user has, over the pre-computed pathway
# cache (populated by `evaluate-visas`). Two goals: a lump sum (investment / golden-visa
# routes, judged on investment_eur) or passive income (retirement & digital-nomad routes,
# judged on the annual income_eur threshold).
FINDER_GOALS: dict[str, dict] = {
    "invest": {"categories": ["investment"], "field": "investment_eur"},
    "income": {"categories": ["retirement", "digital_nomad"], "field": "income_eur"},
}
# Categories the finder relies on — what `evaluate-visas` pre-computes for every country.
FINDER_CATEGORIES = ["investment", "retirement", "digital_nomad"]


def finder(
    db: Session, amount_eur: float, goal: str, *,
    currency: str = "EUR", rate: float = 1.0, lang: str = "en", limit: int = 60,
) -> list[dict]:
    """Rank countries whose `goal` pathway this `amount_eur` clears, best-first. Reads ONLY the
    cached pathway rows (no AI) — so coverage depends on `evaluate-visas` having run. Ranking:
    easiest first (difficulty desc), then least time committed there (min-stay asc, then years
    to citizenship asc)."""
    spec = FINDER_GOALS.get(goal) or FINDER_GOALS["invest"]
    field = spec["field"]
    keys = [_key(c) for c in spec["categories"]]
    rows = db.query(PlaceCustomEval).filter(PlaceCustomEval.key.in_(keys)).all()
    if not rows:
        return []
    place_ids = {r.place_id for r in rows}
    places = {
        p.id: p for p in db.query(Place)
        .filter(Place.id.in_(place_ids), Place.active.is_(True), Place.kind == "country")
        .all()
    }
    out: list[dict] = []
    for r in rows:
        place = places.get(r.place_id)
        if place is None:
            continue
        m = r.meta or {}
        if not m.get("exists"):
            continue
        threshold = m.get(field)
        if threshold is None or threshold > amount_eur:  # no monetary route, or out of reach
            continue
        payload = pathway_payload(r, lang, rate=rate, currency=currency)
        out.append({
            "place_id": place.id,
            "name": place.name,
            "iso_code": place.iso_code,
            "threshold_eur": threshold,
            **payload,
        })

    def _rank(x: dict) -> tuple:
        big = 10**9
        return (
            -(x.get("difficulty") or 0),
            x["min_stay_days"] if x.get("min_stay_days") is not None else big,
            x["citizenship_years"] if x.get("citizenship_years") is not None else big,
        )

    out.sort(key=_rank)
    return out[:limit]
