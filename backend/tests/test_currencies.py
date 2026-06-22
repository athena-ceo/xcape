# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.models.place import Place
from app.models.profile import Profile
from app.models.user import User
from app.services import currencies, fx


def test_default_currency_from_country_iso():
    assert currencies.default_for_iso("US") == "USD"
    assert currencies.default_for_iso("GB") == "GBP"
    assert currencies.default_for_iso("FR") == "EUR"
    assert currencies.default_for_iso("ZZ") == "EUR"   # unknown → fallback
    assert currencies.default_for_iso(None) == "EUR"


def test_effective_currency_prefers_explicit_then_residence(db_session):
    # Explicit profile choice wins.
    user = User(current_country="United States")
    user.profile = Profile(currency="CHF")
    assert currencies.effective_currency(db_session, user) == "CHF"

    # No explicit choice → derive from the country of residence (resolved via the Place table).
    db_session.add(Place(kind="country", name="United States", iso_code="US", attributes={}))
    db_session.commit()
    user2 = User(current_country="United States")
    user2.profile = Profile()
    assert currencies.effective_currency(db_session, user2) == "USD"


def test_fx_eur_is_identity_no_network():
    # EUR short-circuits to 1.0 without any network call.
    assert fx.eur_rate("EUR") == 1.0
    assert fx.from_eur(100, "EUR") == 100
    assert fx.to_eur(100, "EUR") == 100


def test_fx_round_trips_with_fallback_table(monkeypatch):
    # Force the offline path (no network): the built-in fallback is used and from/to are inverse.
    monkeypatch.setattr(fx, "_fetch", lambda: None)
    monkeypatch.setitem(fx._cache, "rates", None)
    monkeypatch.setitem(fx._cache, "day", None)
    rate = fx.eur_rate("USD")
    assert rate == fx._FALLBACK["USD"] and rate > 0
    assert round(fx.to_eur(fx.from_eur(250, "USD"), "USD")) == 250
