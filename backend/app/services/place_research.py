# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""AI-backed enrichment of the place database (cache-first).

Called only on a cache miss or an explicit refresh; results are written back to
Place / MediaAsset so subsequent reads are instant. Uses the Responses API with web
search + structured output (see services.ai_client).
"""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.media import MediaAsset
from app.models.place import Place
from app.services import ai_client, criteria


def normalize_url(url: str) -> str:
    """Canonical form for de-duplication: scheme+host lowercased, no utm_* params, no
    trailing slash. Only the URL identifies a resource — the title doesn't matter."""
    try:
        p = urlparse(str(url).strip())
        query = "&".join(
            q for q in p.query.split("&") if q and not q.lower().startswith("utm_")
        )
        path = p.path.rstrip("/")
        return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", query, ""))
    except Exception:
        return str(url).strip().rstrip("/")

# The attribute vocabulary the seed data uses — keep AI output on the same scale.
_ENUMS: dict[str, list[str]] = {
    "cost_of_living": ["low", "medium", "high"],
    "climate": ["cold", "temperate", "mild", "warm", "tropical"],
    "language_ease": ["french", "english", "easy", "medium", "hard"],
    "healthcare": ["strong", "good", "basic"],
    "education": ["strong", "good", "basic"],
    "safety": ["high", "medium", "low"],
    "political_stability": ["high", "medium", "low"],
    "openness": ["high", "medium", "low"],
    "gender_equality": ["high", "medium", "low"],
    "tax": ["low", "medium", "high"],
    # How widely a newcomer can get by in English day-to-day (services, work, daily life).
    "english": ["widely", "moderate", "limited"],
    # How the country taxes a tax-resident's income: only locally-sourced (territorial), all
    # worldwide income (worldwide), or a mix / special-regime (hybrid).
    "tax_basis": ["territorial", "worldwide", "hybrid"],
    "visa": ["easy", "medium", "hard"],
    "expat_community": ["large", "medium", "small"],
    "culture": ["high", "medium", "low"],
    "food": ["high", "medium", "low"],
    "nature": ["high", "medium", "low"],
    "internet": ["fast", "ok", "slow"],
}

# Acceptance of specific communities (the inclusion criterion scores the worst of the
# ones the user cares about). high = welcoming, mixed = uneven, low = hostile.
_GROUP_LEVELS = ["high", "mixed", "low"]

_SYSTEM = (
    "You assess countries for someone relocating internationally as a foreign resident. Use "
    "web search for current facts. This data is shared across users, so stay origin-neutral: "
    "do NOT assume any particular home country or citizenship (per-user visa/language scoring "
    "is applied separately). Rate each attribute on the given scale. For social_acceptance, "
    "rate how welcome each community is in daily life, anchored on evidence (e.g. ILGA "
    "for LGBTQ+ rights, antisemitism / Islamophobia monitoring reports, discrimination "
    "and integration indices) rather than impressions. For gender_equality use signals "
    "like the Global Gender Gap Index (legal rights, equal pay, safety). openness is the "
    "society's general tolerance toward minorities overall. For english, judge how far a "
    "newcomer who speaks only English can manage daily life (widely = English is broadly "
    "usable in services and work; limited = little English outside tourism). For tax_basis, "
    "classify how the country taxes a tax-RESIDENT's income: territorial = only locally-sourced "
    "income is taxed, worldwide = worldwide income is taxed, hybrid = a mix or a special "
    "non-dom / remittance regime."
)

# Bump when the per-criterion DETAIL prompt below changes in a way that should invalidate the
# cached explanation text. Entries are stamped with this; detail_map ignores entries from an
# older version, so they're treated as missing and regenerated on the next drilldown.
DETAIL_PROMPT_VERSION = "4"  # v4: neutral newcomer framing (no forced eligibility) + visa pathways


def _place_schema() -> dict:
    attr_props: dict = {k: {"type": "string", "enum": v} for k, v in _ENUMS.items()}
    # Languages a resident actually uses (official + widely-spoken English where usable).
    attr_props["languages"] = {"type": "array", "items": {"type": "string"}}
    # Per-community acceptance, judged from evidence (see _SYSTEM).
    attr_props["social_acceptance"] = {
        "type": "object",
        "properties": {g: {"type": "string", "enum": _GROUP_LEVELS} for g in criteria.community_keys()},
        "required": criteria.community_keys(),
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "iso_code": {"type": "string"},
            "attributes": {
                "type": "object",
                "properties": attr_props,
                "required": [*_ENUMS.keys(), "languages", "social_acceptance"],
                "additionalProperties": False,
            },
            "summary_fr": {"type": "string"},
            "summary_en": {"type": "string"},
        },
        "required": ["name", "iso_code", "attributes", "summary_fr", "summary_en"],
        "additionalProperties": False,
    }


def research_place(db: Session, name: str, *, user_id: int | None = None) -> Place | None:
    """Look up a country not yet in the DB, structure its attributes, cache it."""
    # Reuse an existing row if it appeared since the caller checked.
    existing = db.query(Place).filter(Place.kind == "country", Place.name.ilike(name)).first()
    if existing:
        return existing

    data = ai_client.respond_json(
        f"Assess the country '{name}' for relocation. Provide all attributes, ISO code, "
        f"and a one-sentence summary in French and English.",
        _place_schema(),
        schema_name="place",
        web_search=True,
        system=_SYSTEM,
        model=settings.openai_chat_model,  # cheaper model — structured ratings, not long prose
        kind="research",
        db=db,
        user_id=user_id,
    )
    # Dedup by ISO: the DB may already hold this country under a different (localized) name —
    # e.g. searching "Spain" when the seed has "Espagne" (both ES). Never create a second row
    # for the same country; reuse the existing one (back-filling any attributes it lacks).
    iso = (data.get("iso_code") or "").upper().strip()
    if iso:
        existing = (
            db.query(Place)
            .filter(Place.kind == "country", func.upper(Place.iso_code) == iso)
            .first()
        )
        if existing:
            return existing
    place = Place(
        kind="country",
        name=data["name"],
        iso_code=iso or data.get("iso_code"),
        attributes=data.get("attributes", {}),
        summary_fr=data.get("summary_fr"),
        summary_en=data.get("summary_en"),
        source="ai",
    )
    db.add(place)
    db.commit()
    db.refresh(place)
    return place


# Criteria with no single scalar attribute — derived from other fields, so they can't be
# back-filled as one value (inclusion is computed from social_acceptance / openness).
_DERIVED_CRITERIA = {"inclusion"}


def _attr_schema(keys: list[str]) -> dict:
    """JSON schema for a subset of AI-derivable place attributes (enums + languages + the
    per-community acceptance object), so any missing ones can be filled in one call."""
    props: dict = {}
    for k in keys:
        if k == "languages":
            props[k] = {"type": "array", "items": {"type": "string"}}
        elif k == "social_acceptance":
            props[k] = {
                "type": "object",
                "properties": {g: {"type": "string", "enum": _GROUP_LEVELS} for g in criteria.community_keys()},
                "required": criteria.community_keys(),
                "additionalProperties": False,
            }
        else:
            props[k] = {"type": "string", **({"enum": _ENUMS[k]} if k in _ENUMS else {})}
    return {"type": "object", "properties": props, "required": keys, "additionalProperties": False}


# Every attribute the AI derives for a country (the seed's scalar enums + languages + the
# per-community acceptance map). Whatever a place is missing gets filled — lazily on view or in
# bulk via `generate` — never bulk-precomputed eagerly for the ~218 countries nobody opens.
def _all_attrs() -> list[str]:
    return [*_ENUMS.keys(), "languages", "social_acceptance"]


def fill_missing_attributes(db: Session, place: Place, *, force: bool = False,
                            user_id: int | None = None) -> int:
    """Fill any MISSING AI-derivable attributes for a place in ONE call (cache-first). Returns 1
    if a call was made, else 0. `force` refills every attribute. Cheaper than per-attribute fills
    and the single place where bulk/on-view attribute generation goes through."""
    have = place.attributes or {}
    targets = _all_attrs()
    missing = targets if force else [k for k in targets if k not in have]
    if not missing:
        return 0
    data = ai_client.respond_json(
        f"Assess {place.name} for someone relocating there. Rate each attribute on its scale.",
        _attr_schema(missing),
        schema_name="place_attrs",
        web_search=True,
        system=_SYSTEM,
        model=settings.openai_chat_model,  # cheaper model — scalar ratings, not prose
        kind="research",
        db=db,
        user_id=user_id,
    )
    attrs = dict(have)
    for k in missing:
        if k in data and data[k] is not None:
            attrs[k] = data[k]
    place.attributes = attrs
    place.source = place.source or "ai"
    db.commit()
    return 1


def fill_criterion(db: Session, place: Place, key: str, *, user_id: int | None = None) -> str | None:
    """Research a single missing attribute for a place and cache it on the Place."""
    if key in _DERIVED_CRITERIA:
        return None  # not a scalar attribute; filled via full research / backfill
    if key in (place.attributes or {}):
        return place.attributes[key]
    enum = _ENUMS.get(key)
    schema = {
        "type": "object",
        "properties": {"value": {"type": "string", **({"enum": enum} if enum else {})}},
        "required": ["value"],
        "additionalProperties": False,
    }
    data = ai_client.respond_json(
        f"For someone relocating to {place.name}, what is the value of '{key}'"
        + (f" on the scale {enum}?" if enum else "?"),
        schema,
        schema_name="criterion",
        web_search=True,
        system=_SYSTEM,
        kind="research",
        db=db,
        user_id=user_id,
    )
    value = data.get("value")
    attrs = dict(place.attributes or {})
    attrs[key] = value
    place.attributes = attrs
    place.source = place.source or "ai"
    db.commit()
    return value


def detail_map(place: Place) -> dict[str, dict]:
    """Normalize `place.criteria_detail` to a per-key map {key: {summary_fr, summary_en,
    sources}}, accepting BOTH the new per-key shape and the legacy bulk `{"criteria":[...]}`
    blob (per-key entries win). The single reader of cached per-criterion detail text."""
    raw = place.criteria_detail or {}
    out: dict[str, dict] = {}
    # Only entries produced by the CURRENT prompt version count; older/unversioned ones are
    # treated as absent so a prompt change transparently regenerates them.
    for key, val in raw.items():
        if key != "criteria" and isinstance(val, dict) and val.get("v") == DETAIL_PROMPT_VERSION:
            out[key] = val
    return out


def _one_detail_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "summary_fr": {"type": "string"},
            "summary_en": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary_fr", "summary_en", "sources"],
        "additionalProperties": False,
    }


def criterion_detail_one(
    db: Session, place: Place, key: str, *, user_id: int | None = None, force: bool = False
) -> dict | None:
    """Generate (cache-first) the explanation text for ONE computed criterion (cost, climate,
    language, visa, inclusion …) and cache it per-key on `place.criteria_detail`. Bilingual +
    sources. Returns the entry, or None if AI is unavailable. Never touches place_custom_evals,
    so it can't disturb the deterministic computed scores. `force` regenerates even if cached."""
    existing = detail_map(place)
    if key in existing and not force:
        return existing[key]
    label = criteria.label(key, "en")
    # Visa is the one origin-specific case; since this text is a SHARED cache it can't be
    # personalised, so describe the country's residence PATHWAYS in general (the per-user score
    # is computed separately). Everything else: the practical reality for a settled newcomer,
    # noting a newcomer-specific angle only where it genuinely applies (no forced "eligibility"
    # language on things like cost of living or climate).
    if key == "visa":
        angle = (
            "summarise the main residence pathways available (e.g. work/skilled, retirement, "
            "investment, family, ancestry, digital-nomad) and roughly how accessible they are, "
            "WITHOUT assuming the reader's nationality"
        )
    else:
        angle = (
            "describe the practical reality for a foreign resident settling in, including a "
            "newcomer-specific angle (cost to non-citizens, when one qualifies, or language) only "
            "where it genuinely applies — not generic boilerplate"
        )
    try:
        data = ai_client.respond_json(
            f"For someone moving to {place.name} as a FOREIGN RESIDENT (a newcomer, not a native "
            f"citizen), write a concise, factual 1-2 sentence explanation of \"{label}\": {angle}. "
            f"Provide BOTH a French version (summary_fr) and an English version (summary_en). Use "
            f"web search and favour the most recent data (2025–2026). Put sources ONLY in the "
            f"sources array, each a plain bare URL (https://…, no Markdown, no tracking params). "
            f"Do NOT put URLs inside the summaries.",
            _one_detail_schema(),
            schema_name="criterion_detail",
            web_search=True,
            model=settings.openai_chat_model,  # lightweight text → faster model
            system=_SYSTEM,
            kind="research",
            db=db,
            user_id=user_id,
        )
    except ai_client.AIUnavailable:
        return None
    entry = {"summary_fr": data.get("summary_fr"), "summary_en": data.get("summary_en"),
             "sources": data.get("sources", []), "v": DETAIL_PROMPT_VERSION}
    # Reassign a new dict so SQLAlchemy detects the JSON change; preserve any existing entries.
    cache = dict(place.criteria_detail or {})
    cache[key] = entry
    place.criteria_detail = cache
    db.commit()
    return entry


def fetch_media(db: Session, place: Place, *, user_id: int | None = None) -> list[MediaAsset]:
    """Discover a map link, useful links and photo references for a place; cache them."""
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["map", "photo", "link"]},
                        "url": {"type": "string"},
                        "caption": {"type": "string"},
                        "source": {"type": "string"},
                    },
                    "required": ["type", "url", "caption", "source"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }
    data = ai_client.respond_json(
        f"Find up to 6 useful resources for someone considering moving to {place.name}: "
        f"a Google Maps link, official tourism/relocation links, and references to "
        f"representative photos. Provide working URLs.",
        schema,
        schema_name="media",
        web_search=True,
        kind="media",
        db=db,
        user_id=user_id,
    )
    seen = {
        normalize_url(m.url)
        for m in db.query(MediaAsset).filter(MediaAsset.place_id == place.id)
    }
    assets: list[MediaAsset] = []
    for item in data.get("items", []):
        url = item.get("url")
        if not url:
            continue
        nu = normalize_url(url)
        if nu in seen:  # same resource (ignore differing titles)
            continue
        seen.add(nu)
        asset = MediaAsset(
            place_id=place.id,
            type=item.get("type", "link"),
            url=url,
            caption=item.get("caption"),
            source=item.get("source"),
        )
        db.add(asset)
        assets.append(asset)
    db.commit()
    for a in assets:
        db.refresh(a)
    return assets
