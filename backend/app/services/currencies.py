# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Default currency for a user, derived from where they live.

The app's money used to be implicitly euros, which only makes sense for people in the eurozone.
The user's currency is now a profile parameter they can edit; when unset we derive a sensible
default from their country of residence (e.g. United States → USD, United Kingdom → GBP). The
mapping is ISO-3166 alpha-2 → ISO-4217, covering the common relocation/residence countries; any
country not listed falls back to EUR. See `fx` for the conversion rates.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import User

# Country of residence (ISO-3166 alpha-2) → currency (ISO-4217). Eurozone members map to EUR.
COUNTRY_CURRENCY: dict[str, str] = {
    # Eurozone
    "AT": "EUR", "BE": "EUR", "HR": "EUR", "CY": "EUR", "EE": "EUR", "FI": "EUR", "FR": "EUR",
    "DE": "EUR", "GR": "EUR", "IE": "EUR", "IT": "EUR", "LV": "EUR", "LT": "EUR", "LU": "EUR",
    "MT": "EUR", "NL": "EUR", "PT": "EUR", "SK": "EUR", "SI": "EUR", "ES": "EUR",
    # Rest of Europe
    "GB": "GBP", "CH": "CHF", "SE": "SEK", "NO": "NOK", "DK": "DKK", "PL": "PLN", "CZ": "CZK",
    "HU": "HUF", "RO": "RON", "BG": "BGN", "IS": "ISK", "UA": "UAH", "RU": "RUB", "RS": "RSD",
    "TR": "TRY",
    # Americas
    "US": "USD", "CA": "CAD", "MX": "MXN", "BR": "BRL", "AR": "ARS", "CL": "CLP", "CO": "COP",
    "PE": "PEN", "UY": "UYU", "PA": "USD", "CR": "CRC", "EC": "USD",
    # Middle East / Africa
    "AE": "AED", "SA": "SAR", "QA": "QAR", "IL": "ILS", "ZA": "ZAR", "EG": "EGP", "MA": "MAD",
    "KE": "KES", "NG": "NGN",
    # Asia / Pacific
    "AU": "AUD", "NZ": "NZD", "JP": "JPY", "CN": "CNY", "HK": "HKD", "SG": "SGD", "KR": "KRW",
    "TW": "TWD", "TH": "THB", "MY": "MYR", "ID": "IDR", "PH": "PHP", "VN": "VND", "IN": "INR",
}

DEFAULT = "EUR"


def default_for_iso(iso: str | None) -> str:
    return COUNTRY_CURRENCY.get((iso or "").upper(), DEFAULT)


def effective_currency(db: Session, user: User | None) -> str:
    """The user's budgeting currency: their explicit profile choice, else derived from their
    country of residence, else EUR."""
    prof = getattr(user, "profile", None) if user else None
    chosen = getattr(prof, "currency", None) if prof else None
    if chosen:
        return str(chosen).upper()
    # Derive from residence. Resolve the country name to a Place to get its ISO code (cache-only).
    from app.services.comparison import get_current_country_place

    place = get_current_country_place(db, user) if user else None
    return default_for_iso(place.iso_code if place else None)
