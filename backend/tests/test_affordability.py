# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.models.custom_eval import PlaceCustomEval
from app.models.place import Place
from app.models.profile import Profile
from app.models.user import User
from app.services import affordability, ai_client

# Single-person monthly cost breakdown the AI would return (euros).
_BREAKDOWN = {
    "rent_eur": 800, "utilities_eur": 150, "food_eur": 300,
    "healthcare_eur": 100, "transport_eur": 80, "other_eur": 170,  # total 1600
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
    # Cache-first: a second call returns the same row without another AI call.
    ev2 = affordability.evaluate_breakdown(db_session, place)
    assert calls["n"] == 1 and ev2.id == ev.id


def test_compute_surplus_and_verdict(db_session, monkeypatch):
    monkeypatch.setattr(ai_client, "respond_json", lambda *a, **k: _BREAKDOWN)
    place = _country(db_session)
    affordability.evaluate_breakdown(db_session, place)

    # Single person, comfortable budget → surplus and a "comfortable" verdict.
    rich = affordability.compute(db_session, place, None, budget_monthly=3000, household_size=1)
    assert rich["pending"] is False
    assert rich["cost_total_eur"] == 1600           # no household scaling at size 1
    assert rich["surplus_eur"] == 1400
    assert rich["verdict"] == "comfortable"

    # Same budget, larger household → costs rise, verdict degrades.
    family = affordability.compute(db_session, place, None, budget_monthly=3000, household_size=4)
    assert family["cost_total_eur"] > rich["cost_total_eur"]
    assert family["verdict"] in ("manageable", "tight", "insufficient")

    # A budget below local costs → deficit + "insufficient".
    poor = affordability.compute(db_session, place, None, budget_monthly=1000, household_size=1)
    assert poor["surplus_eur"] == -600 and poor["verdict"] == "insufficient"


def test_compute_pending_without_breakdown(db_session):
    place = _country(db_session)  # nothing cached
    out = affordability.compute(db_session, place, None, budget_monthly=2000, household_size=1)
    assert out["pending"] is True and "cost_total_eur" not in out
    assert out["annual_income_eur"] == 24000  # tie-in still computed


def test_income_pathways_tie_in(db_session):
    place = _country(db_session)
    # A cached retirement pathway with a 24k/yr income threshold.
    db_session.add(PlaceCustomEval(
        place_id=place.id, key="visa_retirement", label="Retirement", score=70, level="good",
        meta={"category": "retirement", "exists": True, "income_eur": 24000}))
    db_session.commit()

    qualifies = affordability.income_pathways(db_session, place.id, annual_income=30000)
    assert qualifies[0]["category"] == "retirement" and qualifies[0]["qualifies"] is True
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
    assert r2["cost_total_eur"] == 1600 and r2["verdict"] == "comfortable"
    assert len(r2["breakdown"]) == len(affordability.COMPONENTS)
