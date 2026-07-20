# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Resolve a new user's current country (the place they're moving from).

Order of preference, per product spec:
  1. Geolocation of the client IP (best-effort, short timeout).
  2. The country implied by their locale (fr -> France, en_gb -> UK, ...).
  3. France.
"""

from __future__ import annotations

import ipaddress
import json
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import httpx

DEFAULT_COUNTRY = "France"

# --- Great-circle distance between countries (for the proximity criterion) -------------
_CENTROIDS_FILE = Path(__file__).resolve().parent.parent / "data" / "country_centroids.json"


@lru_cache(maxsize=1)
def _centroids() -> dict[str, list]:
    return json.loads(_CENTROIDS_FILE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _centroid_by_name() -> dict[str, str]:
    """Lowercased country name → ISO2 (to resolve the user's current_country text)."""
    return {row[2].lower(): iso for iso, row in _centroids().items()}


def _resolve_centroid(value: str | None) -> tuple[float, float] | None:
    """Resolve an ISO2 code or a country name to (lat, lon)."""
    if not value:
        return None
    v = str(value).strip()
    row = _centroids().get(v.upper()) or _centroids().get(_centroid_by_name().get(v.lower(), ""))
    return (row[0], row[1]) if row else None


def distance_between(origin: str | None, dest: str | None) -> float | None:
    """Distance in km between two countries (each an ISO2 code or name), or None if either
    centroid is unknown (proximity then falls back to neutral)."""
    a, b = _resolve_centroid(origin), _resolve_centroid(dest)
    if a is None or b is None:
        return None
    lat1, lon1, lat2, lon2 = map(radians, [a[0], a[1], b[0], b[1]])
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(h))  # km


def iso2_of(value: str | None) -> str | None:
    """Uppercase ISO2 for an ISO2 code or country name, or None if unresolvable. Used as the
    stable anchor key for family-proximity travel notes regardless of how the user typed it."""
    if not value:
        return None
    v = str(value).strip()
    if _centroids().get(v.upper()):
        return v.upper()
    return _centroid_by_name().get(v.lower())


def country_name(value: str | None) -> str | None:
    """Display country name for an ISO2 code (echoes back an already-given name)."""
    iso = iso2_of(value)
    row = _centroids().get(iso) if iso else None
    return row[2] if row else (str(value).strip() if value else None)


# --- Travel effort between countries (for the proximity criteria) ---------------------
# Great-circle km is a poor proxy for how reachable a place is; what matters for staying near
# family is door-to-door TRAVEL TIME by the most sensible means. We model it deterministically
# from centroid distance and take whichever mode is faster: short hops go overland (rail/road,
# no airport overhead), longer trips fly (fixed airport/ground overhead + cruise), and very long
# trips add a connection penalty. Taking the min keeps the estimate monotonic in distance — a
# closer country never scores worse than a farther one. Cost can't be priced without live data,
# so we return a coarse band (low/medium/high), never an invented figure.
_LAND_MAX_KM = 1000.0       # beyond this, overland travel stops being sensible
_LAND_KMH = 90.0            # effective door-to-door overland speed (incl. stops/transfers)
_FLIGHT_OVERHEAD_H = 3.0    # airport + ground time either end of a flight
_CRUISE_KMH = 750.0         # effective air cruise speed
_CONNECTION_KM = 9000.0     # beyond this a direct flight is unlikely → add a layover
_CONNECTION_PENALTY_H = 2.5


def travel_estimate(origin: str | None, dest: str | None) -> dict | None:
    """Door-to-door travel time (hours), the sensible mode, and a coarse cost band between two
    countries, or None if either centroid is unknown."""
    d = distance_between(origin, dest)
    if d is None:
        return None
    flight = _FLIGHT_OVERHEAD_H + d / _CRUISE_KMH + (_CONNECTION_PENALTY_H if d >= _CONNECTION_KM else 0)
    land = (d / _LAND_KMH + 1.0) if d <= _LAND_MAX_KM else None  # +1 h access at each end
    if land is not None and land <= flight:
        hours, mode = land, "land"
    elif d >= _CONNECTION_KM:
        hours, mode = flight, "flight_connection"
    else:
        hours, mode = flight, "flight"
    band = "low" if d <= _LAND_MAX_KM else ("high" if d >= 6000 else "medium")
    return {"km": round(d), "hours": round(hours, 1), "mode": mode, "cost_band": band}


def travel_time_hours(origin: str | None, dest: str | None) -> float | None:
    """Door-to-door travel time in hours by the most sensible means, or None if unknown."""
    est = travel_estimate(origin, dest)
    return est["hours"] if est else None

# Locale (or locale_region) -> country name. Keys are matched lower-cased with
# both '-' and '_' separators normalised to '_'.
_LOCALE_COUNTRY: dict[str, str] = {
    "fr": "France",
    "fr_fr": "France",
    "fr_be": "Belgium",
    "fr_ch": "Switzerland",
    "fr_ca": "Canada",
    "en": "United Kingdom",
    "en_gb": "United Kingdom",
    "en_uk": "United Kingdom",
    "en_us": "United States",
    "en_ca": "Canada",
    "en_au": "Australia",
    "en_ie": "Ireland",
    "es": "Spain",
    "es_es": "Spain",
    "de": "Germany",
    "it": "Italy",
    "pt": "Portugal",
    "nl": "Netherlands",
}


def _country_from_locale(locale: str | None) -> str | None:
    if not locale:
        return None
    key = locale.strip().lower().replace("-", "_")
    if key in _LOCALE_COUNTRY:
        return _LOCALE_COUNTRY[key]
    return _LOCALE_COUNTRY.get(key.split("_", 1)[0])


def _is_geolocatable(ip: str | None) -> bool:
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved)


def _country_from_ip(ip: str) -> str | None:
    try:
        resp = httpx.get(f"https://ipapi.co/{ip}/country_name/", timeout=2.0)
        if resp.status_code == 200:
            name = resp.text.strip()
            # ipapi returns an error blob (JSON) on failure rather than a name.
            if name and "{" not in name and len(name) < 80:
                return name
    except httpx.HTTPError:
        pass
    return None


def resolve_current_country(client_ip: str | None, locale: str | None) -> str:
    if _is_geolocatable(client_ip):
        by_ip = _country_from_ip(client_ip)  # type: ignore[arg-type]
        if by_ip:
            return by_ip
    return _country_from_locale(locale) or DEFAULT_COUNTRY


def client_ip_from_request(headers, fallback: str | None) -> str | None:
    """Prefer the real client IP from X-Forwarded-For (set by the external nginx)."""
    xff = headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return fallback
