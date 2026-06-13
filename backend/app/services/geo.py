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

import httpx

DEFAULT_COUNTRY = "France"

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
