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


# Geographic subregion by ISO-2 — the way people actually think about regions ("Western
# Europe", not the World Bank's "Europe & Central Asia"). Europe is covered precisely (our
# main user base); other countries fall back to a friendly continent label below. Offline +
# deterministic (the deprecated restcountries API is no longer reliable).
_SUBREGION: dict[str, str] = {}
for _names, _codes in {
    "Western Europe": "AT BE FR DE LI LU MC NL CH",
    "Northern Europe": "DK EE FI IS IE LV LT NO SE GB FO GG IM JE AX",
    "Southern Europe": "AL AD BA HR GR IT MT ME MK PT SM RS SI ES VA GI XK CY",
    "Central & Eastern Europe": "BG BY CZ HU MD PL RO RU SK UA",
    "Central Asia": "KZ KG TJ TM UZ",
    "North America": "US CA",
    "Central America & Caribbean": "MX GT BZ SV HN NI CR PA CU DO JM TT BS BB HT PR AG DM GD KN LC VC",
    "South America": "BR AR CL UY PY BO PE EC CO VE GY SR",
    "East Asia": "JP KR KP CN TW HK MO MN",
    "Southeast Asia": "TH VN SG MY ID PH KH LA MM BN TL",
    "South Asia": "IN PK BD LK NP BT MV AF",
    "Middle East": "SA AE QA KW BH OM IL JO LB IQ IR YE SY PS TR AM AZ GE",
    "North Africa": "MA DZ TN LY EG SD",
    "Oceania": "AU NZ FJ PG WS TO VU SB FM KI MH NR PW TV",
}.items():
    for _c in _codes.split():
        _SUBREGION[_c] = _names


def _friendly_region(wb: str | None) -> str | None:
    """A normal continent-level label from the World Bank macro-region (whose exact wording
    changes over time, e.g. it now lumps 'Afghanistan & Pakistan' into MENA). Used only as a
    fallback when a country isn't in the precise subregion map (mostly Sub-Saharan Africa)."""
    if not wb:
        return wb
    s = wb.lower()
    if "europe" in s:
        return "Europe"
    if "north america" in s:
        return "North America"
    if "latin america" in s or "caribbean" in s:
        return "Latin America & Caribbean"
    if "north africa" in s or "middle east" in s:
        return "Middle East & North Africa"
    if "sub-saharan" in s or "africa" in s:
        return "Sub-Saharan Africa"
    if "south asia" in s:
        return "South Asia"
    if "east asia" in s or "pacific" in s:
        return "Asia & Pacific"
    return wb


def _wikipedia_image(title: str) -> str | None:
    data = _get_json(
        f"https://en.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}"
    )
    if isinstance(data, dict):
        return (data.get("originalimage") or data.get("thumbnail") or {}).get("source")
    return None


_FACTS_V = 2  # bump to re-derive cached facts (e.g. the friendly region/subregion)


def get_facts(db: Session, place: Place, *, refresh: bool = False) -> dict:
    if place.facts and not refresh and place.facts.get("facts_v") == _FACTS_V:
        return place.facts
    facts = _world_bank(place)
    # Friendly region: a specific subregion where we have one, else a cleaned macro-region.
    iso = (place.iso_code or "").strip().upper()
    if iso in _SUBREGION:
        facts["subregion"] = _SUBREGION[iso]
    facts["region"] = _friendly_region(facts.get("region"))
    facts["facts_v"] = _FACTS_V
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
