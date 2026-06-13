# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Basic country facts for the drill-down (capital, population, region, coordinates,
flag, a representative photo), cached on the Place.

Keyless, reliable sources: the World Bank country + population APIs for structured
facts and coordinates, flagcdn for flags, and the Wikipedia REST summary for a lead
image. All best-effort — partial facts are fine and the result is cached so we only hit
the network once per place.
"""

from __future__ import annotations

import httpx
from sqlalchemy.orm import Session

from app.models.place import Place

_WB = "https://api.worldbank.org/v2"


def _osm_embed_bbox(lat: float, lng: float, pad: float = 6.0) -> str:
    return f"{lng - pad},{lat - pad},{lng + pad},{lat + pad}"


# Wikimedia rejects requests without a descriptive User-Agent.
_UA = "xCape/1.0 (relocation app; https://apps.athenadecisions.com/xcape)"


def _get_json(url: str, params: dict | None = None):
    try:
        resp = httpx.get(
            url, params=params, timeout=8.0, follow_redirects=True,
            headers={"User-Agent": _UA, "accept": "application/json"},
        )
        if resp.status_code == 200:
            return resp.json()
    except (httpx.HTTPError, ValueError):
        pass
    return None


def _world_bank(place: Place) -> dict:
    code = (place.iso_code or "").strip()
    if not code:
        return {}
    facts: dict = {}
    country = _get_json(f"{_WB}/country/{code}", {"format": "json"})
    try:
        row = country[1][0]
        facts["capital"] = row.get("capitalCity") or None
        facts["region"] = (row.get("region") or {}).get("value")
        lat, lng = float(row["latitude"]), float(row["longitude"])
        facts["lat"], facts["lng"] = lat, lng
        facts["osm_bbox"] = _osm_embed_bbox(lat, lng)
    except (TypeError, IndexError, KeyError, ValueError):
        pass

    pop = _get_json(
        f"{_WB}/country/{code}/indicator/SP.POP.TOTL", {"format": "json", "mrnev": "1"}
    )
    try:
        facts["population"] = pop[1][0]["value"]
    except (TypeError, IndexError, KeyError):
        pass
    return facts


def _wikipedia_image(title: str) -> str | None:
    data = _get_json(
        f"https://en.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}"
    )
    if isinstance(data, dict):
        return (data.get("originalimage") or data.get("thumbnail") or {}).get("source")
    return None


def get_facts(db: Session, place: Place, *, refresh: bool = False) -> dict:
    if place.facts and not refresh:
        return place.facts
    facts = _world_bank(place)
    code = (place.iso_code or "").strip().lower()
    if len(code) == 2:
        facts["flag"] = f"https://flagcdn.com/w320/{code}.png"
    # Prefer the capital's lead image (a real skyline/scenery photo) over the country
    # page's (often just the flag); fall back to the country.
    capital = facts.get("capital")
    image = (_wikipedia_image(capital) if capital else None) or _wikipedia_image(place.name)
    if image:
        facts["image"] = image
    place.facts = facts
    db.commit()
    return facts
