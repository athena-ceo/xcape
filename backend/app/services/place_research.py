# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""AI-backed enrichment of the place database (cache-first).

Called only on a cache miss or an explicit refresh; results are written back to
Place / MediaAsset so subsequent reads are instant. Uses the Responses API with web
search + structured output (see services.ai_client).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.media import MediaAsset
from app.models.place import Place
from app.services import ai_client

# The attribute vocabulary the seed data uses — keep AI output on the same scale.
_ENUMS: dict[str, list[str]] = {
    "cost_of_living": ["low", "medium", "high"],
    "climate": ["cold", "temperate", "mild", "warm", "tropical"],
    "language_ease": ["french", "english", "easy", "medium", "hard"],
    "healthcare": ["strong", "good", "basic"],
    "safety": ["high", "medium", "low"],
    "political_stability": ["high", "medium", "low"],
    "tax": ["low", "medium", "high"],
    "visa": ["easy", "medium", "hard"],
    "expat_community": ["large", "medium", "small"],
    "nature": ["high", "medium", "low"],
    "internet": ["fast", "ok", "slow"],
}

_SYSTEM = (
    "You assess countries for someone relocating from France. Use web search for "
    "current facts. Rate each attribute on the given scale; language_ease and visa "
    "are judged from the perspective of a French/EU citizen."
)


def _place_schema() -> dict:
    attr_props: dict = {k: {"type": "string", "enum": v} for k, v in _ENUMS.items()}
    # Languages a resident actually uses (official + widely-spoken English where usable).
    attr_props["languages"] = {"type": "array", "items": {"type": "string"}}
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "iso_code": {"type": "string"},
            "attributes": {
                "type": "object",
                "properties": attr_props,
                "required": [*_ENUMS.keys(), "languages"],
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


def fill_criterion(db: Session, place: Place, key: str, *, user_id: int | None = None) -> str | None:
    """Research a single missing attribute for a place and cache it on the Place."""
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
    assets: list[MediaAsset] = []
    for item in data.get("items", []):
        asset = MediaAsset(
            place_id=place.id,
            type=item.get("type", "link"),
            url=item["url"],
            caption=item.get("caption"),
            source=item.get("source"),
        )
        db.add(asset)
        assets.append(asset)
    db.commit()
    for a in assets:
        db.refresh(a)
    return assets
