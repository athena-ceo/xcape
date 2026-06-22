# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Currency conversion for budgeting — EUR-based reference rates.

Our shared country data (the cost breakdown and the visa income/investment thresholds) is cached
in EUR and shared across all users, so a user's budget — entered in THEIR currency — is compared
and displayed by converting at read time. Rates are EUR-based (1 EUR = `rate` units of the target
currency), fetched once per day from the European Central Bank via the keyless Frankfurter API and
cached in-process. If the fetch fails we fall back to a built-in table so budgeting never breaks.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import httpx

# Approximate EUR-based fallback rates (1 EUR = N units), used only when the live fetch fails.
# Deliberately rough — the costs themselves are estimates; this just keeps the feature working.
_FALLBACK: dict[str, float] = {
    "EUR": 1.0, "USD": 1.08, "GBP": 0.85, "CHF": 0.96, "CAD": 1.47, "AUD": 1.65, "NZD": 1.78,
    "JPY": 170.0, "SGD": 1.45, "HKD": 8.45, "SEK": 11.3, "NOK": 11.7, "DKK": 7.46, "PLN": 4.30,
    "CZK": 25.2, "HUF": 395.0, "RON": 4.97, "BGN": 1.96, "AED": 3.97, "SAR": 4.05, "QAR": 3.93,
    "ZAR": 19.8, "BRL": 6.00, "MXN": 20.3, "INR": 90.0, "CNY": 7.80, "THB": 39.0, "TRY": 35.0,
    "ILS": 4.00, "KRW": 1480.0, "PHP": 62.0, "IDR": 17500.0, "MYR": 5.10, "VND": 27000.0,
    "EGP": 53.0, "MAD": 10.8, "CLP": 1020.0, "COP": 4400.0, "PEN": 4.10, "ARS": 1000.0,
    "TWD": 35.0, "RUB": 95.0, "UAH": 45.0,
}

_FRANKFURTER = "https://api.frankfurter.app/latest"

# In-process daily cache: {"rates": {...}, "day": "YYYY-MM-DD"}. Refetched once per UTC day.
_cache: dict = {"rates": None, "day": None}


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _fetch() -> dict[str, float] | None:
    """Best-effort EUR-based rates from the ECB (Frankfurter). None on any failure."""
    try:
        resp = httpx.get(_FRANKFURTER, params={"from": "EUR"}, timeout=6.0)
        if resp.status_code != 200:
            return None
        data = resp.json()
        rates = {str(k).upper(): float(v) for k, v in (data.get("rates") or {}).items()}
        rates["EUR"] = 1.0
        return rates if rates.get("USD") else None  # sanity check the payload looks real
    except (httpx.HTTPError, ValueError, TypeError):
        return None


def rates() -> dict[str, float]:
    """EUR-based rates (1 EUR = N units), cached per day. Live ECB rates, else the fallback table."""
    today = _today()
    if _cache["rates"] is not None and _cache["day"] == today:
        return _cache["rates"]
    live = _fetch()
    # Layer live rates over the fallback so currencies the ECB omits still convert.
    merged = {**_FALLBACK, **(live or {})}
    _cache["rates"], _cache["day"] = merged, today
    return merged


def eur_rate(currency: str | None) -> float:
    """Units of `currency` per 1 EUR (1.0 for EUR / unknown — EUR short-circuits, no network)."""
    cur = (currency or "EUR").upper()
    if cur == "EUR":
        return 1.0
    return rates().get(cur, _FALLBACK.get(cur, 1.0))


def from_eur(amount_eur: float, currency: str | None) -> float:
    """Convert an EUR amount into `currency`."""
    return amount_eur * eur_rate(currency)


def to_eur(amount: float, currency: str | None) -> float:
    """Convert an amount in `currency` back into EUR."""
    r = eur_rate(currency)
    return amount / r if r else amount
