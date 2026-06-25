# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.models.custom_eval import PlaceCustomEval
from app.models.place import Place
from app.models.profile import Profile
from app.models.user import User
from app.services import affordability, ai_client, fx

# Single-person monthly cost breakdown the AI would return (euros), with per-component notes.
# rent-based total = 1600 (rent 800); the buy/mortgage housing figure (1100) is cached alongside.
_BREAKDOWN = {
    "rent_eur": 800, "buy_eur": 1100, "utilities_eur": 150, "food_eur": 300,
    "healthcare_eur": 100, "transport_eur": 80, "other_eur": 170,
    **{f"{c}_note_fr": f"note {c} fr" for c in
       ("rent", "buy", "utilities", "food", "healthcare", "transport", "other")},
    **{f"{c}_note_en": f"note {c} en" for c in
       ("rent", "buy", "utilities", "food", "healthcare", "transport", "other")},
    "summary_fr": "fr", "summary_en": "en", "sources": ["https://x.test"],
}


def _country(db_session) -> Place:
    p = Place(kind="country", name="Costaland", iso_code="CL", attributes={})
    db_session.add(p)
    db_session.commit()
    return p


def test_household_factor_scales_per_component():
    # One person → no scaling; rent grows slower than food with each added member.
    assert affordability.household_factor("rent", 1) == 1.0
    assert affordability.household_factor("food", 3) > affordability.household_factor("rent", 3)
    # Healthcare is per-person (linear).
    assert affordability.household_factor("healthcare", 3) == 3.0


def test_housing_scales_by_bedrooms():
    # One bedroom for the primary occupant or couple; one more per additional member.
    assert affordability.bedrooms_for_size(1) == 1
    assert affordability.bedrooms_for_size(2) == 1   # a couple still shares one bedroom
    assert affordability.bedrooms_for_size(3) == 2
    assert affordability.bedrooms_for_size(4) == 3
    # So a couple needs no more housing than a single person...
    assert affordability.household_factor("rent", 2) == affordability.household_factor("rent", 1)
    # ...but each additional person adds a bedroom and raises the housing cost.
    assert affordability.household_factor("rent", 4) > affordability.household_factor("rent", 3)
    # Mortgage (buy) housing scales the same bedroom way.
    assert affordability.household_factor("buy", 4) == affordability.housing_factor(4)


def test_breakdown_reports_bedrooms_for_housing(db_session, monkeypatch):
    monkeypatch.setattr(ai_client, "respond_json", lambda *a, **k: _BREAKDOWN)
    place = _country(db_session)
    affordability.evaluate_breakdown(db_session, place)
    fam = affordability.compute(db_session, place, None, budget_monthly=3000, household_size=4)
    housing = fam["breakdown"][0]
    assert housing["key"] == "rent" and housing["bedrooms"] == 3   # household of 4 → 3 bedrooms
    # Couple → still a single bedroom, so housing cost equals the single-person figure.
    couple = affordability.compute(db_session, place, None, budget_monthly=3000, household_size=2)
    assert couple["breakdown"][0]["bedrooms"] == 1
    assert couple["breakdown"][0]["amount"] == 800


def test_default_household_size_from_type():
    assert affordability.default_household_size(Profile(household_type="single")) == 1
    assert affordability.default_household_size(Profile(household_type="couple")) == 2
    assert affordability.default_household_size(Profile(household_type="family")) == 4
    assert affordability.default_household_size(None) == 1


def test_evaluate_breakdown_caches_meta(db_session, monkeypatch):
    calls = {"n": 0}

    def fake(*a, schema_name=None, **k):
        calls["n"] += 1
        assert schema_name == "cost_breakdown"
        return _BREAKDOWN

    monkeypatch.setattr(ai_client, "respond_json", fake)
    place = _country(db_session)
    ev = affordability.evaluate_breakdown(db_session, place)
    assert ev.key == "cost_breakdown"
    assert ev.meta["total_single_eur"] == 1600
    assert ev.meta["components"]["rent"] == 800
    # Per-component FR/EN justification notes are captured for the explanation popup.
    assert ev.meta["notes"]["rent"] == {"fr": "note rent fr", "en": "note rent en"}
    # Cache-first: a second call returns the same row without another AI call.
    ev2 = affordability.evaluate_breakdown(db_session, place)
    assert calls["n"] == 1 and ev2.id == ev.id


def test_compute_surplus_and_verdict(db_session, monkeypatch):
    monkeypatch.setattr(ai_client, "respond_json", lambda *a, **k: _BREAKDOWN)
    place = _country(db_session)
    affordability.evaluate_breakdown(db_session, place)

    # Single person, comfortable budget → surplus and a "comfortable" verdict. Default currency is
    # EUR (rate 1.0), so the cached EUR figures pass through unchanged.
    rich = affordability.compute(db_session, place, None, budget_monthly=3000, household_size=1)
    assert rich["pending"] is False and rich["currency"] == "EUR"
    assert rich["cost_total"] == 1600           # no household scaling at size 1
    assert rich["surplus"] == 1400
    assert rich["verdict"] == "comfortable"

    # Same budget, larger household → costs rise, verdict degrades.
    family = affordability.compute(db_session, place, None, budget_monthly=3000, household_size=4)
    assert family["cost_total"] > rich["cost_total"]
    assert family["verdict"] in ("manageable", "tight", "insufficient")

    # A budget below local costs → deficit + "insufficient".
    poor = affordability.compute(db_session, place, None, budget_monthly=1000, household_size=1)
    assert poor["surplus"] == -600 and poor["verdict"] == "insufficient"


def test_compute_surfaces_tax_basis_and_us_person(db_session, monkeypatch):
    monkeypatch.setattr(ai_client, "respond_json", lambda *a, **k: _BREAKDOWN)
    place = _country(db_session)
    place.attributes = {"tax_basis": "territorial"}
    db_session.commit()

    # No profile → tax basis still surfaces from the place; us_person is False.
    out = affordability.compute(db_session, place, None, budget_monthly=3000, household_size=1)
    assert out["tax_basis"] == "territorial" and out["us_person"] is False

    # A US-citizen profile flips us_person on (the worldwide-income reminder shows).
    us = Profile(user=User(citizenships=["US"]))
    non_us = Profile(user=User(citizenships=["FR"]))
    assert affordability.compute(db_session, place, us,
                                 budget_monthly=None, household_size=1)["us_person"] is True
    assert affordability.compute(db_session, place, non_us,
                                 budget_monthly=None, household_size=1)["us_person"] is False


def test_compute_converts_to_user_currency(db_session, monkeypatch):
    monkeypatch.setattr(ai_client, "respond_json", lambda *a, **k: _BREAKDOWN)
    place = _country(db_session)
    affordability.evaluate_breakdown(db_session, place)
    # 1 EUR = 2 units of the user's currency → every cached EUR figure doubles for display.
    monkeypatch.setattr(fx, "eur_rate", lambda c: 2.0 if c == "USD" else 1.0)
    out = affordability.compute(
        db_session, place, None, budget_monthly=4000, household_size=1, currency="USD")
    assert out["currency"] == "USD"
    assert out["cost_total"] == 3200            # 1600 EUR × 2
    assert out["surplus"] == 800                # 4000 (USD budget) − 3200
    assert out["breakdown"][0]["amount"] == 1600  # rent 800 EUR × 2


def test_compute_housing_follows_tenure(db_session, monkeypatch):
    monkeypatch.setattr(ai_client, "respond_json", lambda *a, **k: _BREAKDOWN)
    place = _country(db_session)
    affordability.evaluate_breakdown(db_session, place)

    # Buyer → the housing slot is the monthly mortgage (1100), not rent (800).
    buyer = affordability.compute(
        db_session, place, Profile(tenure="buy"), budget_monthly=3000, household_size=1)
    assert buyer["breakdown"][0]["key"] == "buy" and buyer["breakdown"][0]["amount"] == 1100
    assert buyer["cost_total"] == 1900  # 1100 + 150 + 300 + 100 + 80 + 170

    # Renter (and the unspecified default) → rent.
    renter = affordability.compute(
        db_session, place, Profile(tenure="rent"), budget_monthly=3000, household_size=1)
    assert renter["breakdown"][0]["key"] == "rent" and renter["breakdown"][0]["amount"] == 800
    assert renter["cost_total"] == 1600


def test_compute_pending_without_breakdown(db_session):
    place = _country(db_session)  # nothing cached
    out = affordability.compute(db_session, place, None, budget_monthly=2000, household_size=1)
    assert out["pending"] is True and "cost_total" not in out
    assert out["annual_income"] == 24000  # tie-in still computed


def test_income_pathways_tie_in(db_session):
    place = _country(db_session)
    # A cached retirement pathway with a 24k/yr income threshold.
    db_session.add(PlaceCustomEval(
        place_id=place.id, key="visa_retirement", label="Retirement", score=70, level="good",
        meta={"category": "retirement", "exists": True, "income_eur": 24000}))
    db_session.commit()

    qualifies = affordability.income_pathways(db_session, place.id, annual_income=30000)
    assert qualifies[0]["category"] == "retirement" and qualifies[0]["income"] == 24000
    assert qualifies[0]["qualifies"] is True
    below = affordability.income_pathways(db_session, place.id, annual_income=12000)
    assert below[0]["qualifies"] is False


def test_affordability_endpoint_pending_then_filled(auth_client, db_session, monkeypatch):
    place = _country(db_session)
    # Instant payload from cache: no breakdown yet → pending, budget echoed from the query override.
    r = auth_client.get(
        f"/api/v1/places/{place.id}/affordability?lang=en&budget=3000&household=1").json()
    assert r["pending"] is True and r["budget_monthly"] == 3000

    # Generate fills the breakdown on-demand → verdict + scaled breakdown.
    monkeypatch.setattr(ai_client, "respond_json", lambda *a, **k: _BREAKDOWN)
    r2 = auth_client.post(f"/api/v1/places/{place.id}/affordability/generate?lang=en",
                          json={"budget": 3000, "household": 1}).json()
    assert r2["pending"] is False
    assert r2["cost_total"] == 1600 and r2["verdict"] == "comfortable"
    assert len(r2["breakdown"]) == 6  # one housing slot + utilities/food/healthcare/transport/other
    rent = next(b for b in r2["breakdown"] if b["key"] == "rent")
    assert rent["note_en"] == "note rent en" and rent["note_fr"] == "note rent fr"


def test_affordability_force_is_admin_only(auth_client, db_session, monkeypatch):
    place = _country(db_session)
    place.attributes = {"tax_basis": "territorial"}  # already set → no lazy self-heal call to count
    db_session.commit()
    # A regular user cannot force a re-research.
    assert auth_client.post(f"/api/v1/places/{place.id}/affordability/generate?lang=en",
                            json={"force": True}).status_code == 403

    # As admin, force re-runs even when the breakdown is already cached (the regenerate action).
    u = db_session.query(User).filter(User.email == "test@example.com").first()
    u.is_admin = True
    db_session.commit()
    calls = {"n": 0}

    def fake(*a, **k):
        calls["n"] += 1
        return _BREAKDOWN

    monkeypatch.setattr(ai_client, "respond_json", fake)
    auth_client.post(f"/api/v1/places/{place.id}/affordability/generate?lang=en", json={})       # caches
    auth_client.post(f"/api/v1/places/{place.id}/affordability/generate?lang=en",
                     json={"force": True})                                                       # re-runs
    assert calls["n"] == 2


def test_investment_route_tie_in_converts_currency(db_session, monkeypatch):
    """The real-estate tie-in surfaces the investment (golden-visa) threshold, converted from the
    canonical EUR to the VIEWING user's currency — never the generating user's."""
    monkeypatch.setattr(ai_client, "respond_json", lambda *a, **k: _BREAKDOWN)
    place = _country(db_session)
    db_session.add(PlaceCustomEval(
        place_id=place.id, key="visa_investment", label="Investment", score=70, level="good",
        summary_fr="", summary_en="", sources=[],
        meta={"category": "investment", "exists": True, "investment_eur": 250000,
              "program_name": "Golden Visa", "min_stay_days": 0}))
    db_session.commit()
    affordability.evaluate_breakdown(db_session, place)
    monkeypatch.setattr(fx, "eur_rate", lambda c: 2.0 if c == "USD" else 1.0)
    out = affordability.compute(db_session, place, None, budget_monthly=None,
                                household_size=1, currency="USD")
    assert out["investment_route"]["investment"] == 500000  # €250k × 2.0 → the viewer's currency
    assert out["investment_route"]["program_name"] == "Golden Visa"


def test_affordability_self_heals_tax_basis(auth_client, db_session, monkeypatch):
    """Opening the budget panel lazily fills the tax_basis attribute (no bulk backfill needed)."""
    place = _country(db_session)  # attributes={} → tax_basis missing

    def fake(*a, schema_name=None, **k):
        return {"value": "territorial"} if schema_name == "criterion" else _BREAKDOWN

    monkeypatch.setattr(ai_client, "respond_json", fake)
    auth_client.post(f"/api/v1/places/{place.id}/affordability/generate?lang=en", json={})
    db_session.refresh(place)
    assert (place.attributes or {}).get("tax_basis") == "territorial"
