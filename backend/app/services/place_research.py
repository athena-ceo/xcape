# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""AI-backed enrichment of the place database (cache-first).

Called only on a cache miss or an explicit refresh; results are written back to
Place / MediaAsset so subsequent reads are instant. Uses the Responses API with web
search + structured output (see services.ai_client).
"""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

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
    "You assess countries for someone relocating from France. Use web search for "
    "current facts. Rate each attribute on the given scale; language_ease and visa "
    "are judged from the perspective of a French/EU citizen. For social_acceptance, "
    "rate how welcome each community is in daily life, anchored on evidence (e.g. ILGA "
    "for LGBTQ+ rights, antisemitism / Islamophobia monitoring reports, discrimination "
    "and integration indices) rather than impressions. For gender_equality use signals "
    "like the Global Gender Gap Index (legal rights, equal pay, safety). openness is the "
    "society's general tolerance toward minorities overall."
)


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
        kind="research",
        db=db,
        user_id=user_id,
    )
    place = Place(
        kind="country",
        name=data["name"],
        iso_code=data.get("iso_code"),
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


_DETAIL_CRITERIA = [
    "cost_of_living", "climate", "language_ease", "healthcare", "education",
    "safety", "political_stability", "inclusion", "gender_equality", "tax", "visa",
    "culture", "food",
]


def _detail_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "criteria": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "enum": _DETAIL_CRITERIA},
                        "summary_fr": {"type": "string"},
                        "summary_en": {"type": "string"},
                        "sources": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["key", "summary_fr", "summary_en", "sources"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["criteria"],
        "additionalProperties": False,
    }


def fetch_criteria_detail(
    db: Session, place: Place, *, lang: str = "fr", user_id: int | None = None
) -> dict:
    """Per-criterion detail with sources, generated in BOTH languages in one call and
    cached, so switching language is instant (no re-fetch / dynamic translation).
    Returns the requested language projected to a {key, summary, sources} list.
    """
    cache = place.criteria_detail or {}
    if "criteria" not in cache:  # not yet cached in the bilingual format
        cache = ai_client.respond_json(
            f"For someone relocating to {place.name}, write a concise, factual 1-2 sentence "
            f"explanation for each of these criteria: {', '.join(_DETAIL_CRITERIA)}. Provide "
            f"BOTH a French version (summary_fr) and an English version (summary_en). Use web "
            f"search for current facts. Put sources ONLY in the sources array, each a plain bare "
            f"URL (https://… , no Markdown, no link text, no tracking params like utm_source). "
            f"Do NOT put any URL or 'Sources:' note inside the summaries.",
            _detail_schema(),
            schema_name="criteria_detail",
            web_search=True,
            system=_SYSTEM,
            kind="research",
            db=db,
            user_id=user_id,
        )
        place.criteria_detail = cache
        db.commit()

    out = []
    for item in cache.get("criteria", []):
        summary = item.get(f"summary_{lang}") or item.get("summary_en") or item.get("summary_fr", "")
        out.append({"key": item["key"], "summary": summary, "sources": item.get("sources", [])})
    return {"criteria": out}


def detail_map(place: Place) -> dict[str, dict]:
    """Normalize `place.criteria_detail` to a per-key map {key: {summary_fr, summary_en,
    sources}}, accepting BOTH the new per-key shape and the legacy bulk `{"criteria":[...]}`
    blob (per-key entries win). The single reader of cached per-criterion detail text."""
    raw = place.criteria_detail or {}
    out: dict[str, dict] = {}
    for item in raw.get("criteria", []) or []:  # legacy bulk shape
        if isinstance(item, dict) and item.get("key"):
            out[item["key"]] = item
    for key, val in raw.items():  # new per-key shape (wins)
        if key != "criteria" and isinstance(val, dict):
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
    db: Session, place: Place, key: str, *, user_id: int | None = None
) -> dict | None:
    """Generate (cache-first) the explanation text for ONE computed criterion (cost, climate,
    language, visa, inclusion …) and cache it per-key on `place.criteria_detail`. Bilingual +
    sources. Returns the entry, or None if AI is unavailable. Never touches place_custom_evals,
    so it can't disturb the deterministic computed scores."""
    existing = detail_map(place)
    if key in existing:
        return existing[key]
    label = criteria.label(key, "en")
    try:
        data = ai_client.respond_json(
            f"For someone relocating to {place.name}, write a concise, factual 1-2 sentence "
            f"explanation of \"{label}\" there (from a resident's point of view). Provide BOTH "
            f"a French version (summary_fr) and an English version (summary_en). Use web search "
            f"for current facts. Put sources ONLY in the sources array, each a plain bare URL "
            f"(https://…, no Markdown, no tracking params). Do NOT put URLs inside the summaries.",
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
             "sources": data.get("sources", [])}
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
