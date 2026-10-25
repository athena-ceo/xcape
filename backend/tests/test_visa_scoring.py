# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Per-user visa scoring over the shared caches: visa ease from each country's researched
pathways, and visa-programme criteria made moot by free access. Regression for prod
2026-10-25 — Spain/Portugal ranked below Mauritius/Uruguay for a Polish + American retiree
couple, and Portugal missed the top 5 of a US citizen with Polish ancestry."""

from app.models.custom_eval import PlaceCustomEval
from app.models.place import Place
from app.models.profile import Profile
from app.models.user import User
from app.services import board, comparison, criteria
from app.services import shortlist as sl


def _place(db, name, iso, **routes):
    p = Place(kind="country", name=name, iso_code=iso, active=True, attributes={})
    db.add(p)
    db.commit()
    for key, score in routes.items():
        db.add(PlaceCustomEval(place_id=p.id, key=key, label=key, score=score, level="ok",
                               summary_fr="", summary_en="", sources=[],
                               meta={"category": key.removeprefix("visa_"), "exists": score > 0,
                                     "income_eur": 20000, "investment_eur": 500000}))
    db.commit()
    return p


def _profile(citizenships, ancestry=None, persona="retiree", **means):
    return Profile(user=User(citizenships=citizenships, ancestry_countries=ancestry or [], heritages=[]),
                   persona=persona, currency="EUR", **means)


def test_visa_comes_from_researched_route_for_every_country(db_session):
    # No curated seed bucket (like ~190 of 219 countries): the researched route still counts.
    brazil = _place(db_session, "Brazil", "BR", visa_retirement=70, visa_digital_nomad=80)
    vals = sl.per_user_values(db_session, [brazil.id], _profile(["US"]))[brazil.id]
    assert vals["visa"] == 0.7  # retiree → the RETIREMENT route, not the easier nomad one
    other = sl.per_user_values(db_session, [brazil.id], _profile(["US"], persona="neutral"))[brazil.id]
    assert other["visa"] == 0.8  # no persona route → easiest general route


def test_eu_household_moots_visa_programme_criteria(db_session):
    spain = _place(db_session, "Spain", "ES", visa_retirement=75, visa_investment=0)
    prof = _profile(["PL", "US"], annual_income=80000, investable_amount=1500000)
    vals = sl.per_user_values(db_session, [spain.id], prof)[spain.id]
    assert vals["visa"] == 1.0
    # Spain closed its golden visa — irrelevant to a household that can settle freely.
    assert vals["residency_investment"] == 1.0
    assert vals["residency_income"] == 1.0
    assert vals["custom_retirement_visa"] == 1.0 and vals["custom_visa_retraite"] == 1.0


def test_non_eu_household_keeps_programme_criteria(db_session):
    spain = _place(db_session, "Spain", "ES", visa_retirement=75, visa_investment=0)
    prof = _profile(["US"], annual_income=80000, investable_amount=1500000)
    vals = sl.per_user_values(db_session, [spain.id], prof)[spain.id]
    assert vals["visa"] == 0.75
    assert vals["residency_investment"] == 0.25  # no investment route → still counts
    assert "custom_retirement_visa" not in vals  # the AI eval decides


def test_polish_ancestry_lifts_portugal(db_session):
    portugal = _place(db_session, "Portugal", "PT", visa_retirement=75)
    vals = sl.per_user_values(db_session, [portugal.id], _profile(["US"], ancestry=["PL"]))[portugal.id]
    assert vals["visa"] == 0.85


def test_mobility_custom_keys_cover_both_locales():
    keys = criteria.mobility_custom_keys()
    assert "custom_retirement_visa" in keys and "custom_visa_retraite" in keys
    assert "custom_healthcare_for_retirees" not in keys


def test_visa_reason_names_the_passport_and_moot_criteria_say_so(db_session):
    spain = _place(db_session, "Spain", "ES", visa_retirement=75)
    prof = _profile(["PL", "US"], annual_income=80000)
    assert comparison.criterion_reason(spain, prof, "visa") == {"code": "visa_free", "via": "PL"}
    view = board.criteria_view(db_session, spain, prof, [
        {"key": "custom_retirement_visa", "label": "Retirement visa", "weight": 6, "source": "persona"}])
    assert view["reasons"]["custom_retirement_visa"] == {"code": "visa_not_needed"}
    assert view["reasons"]["residency_income"] == {"code": "visa_not_needed"}
    assert "custom_retirement_visa" not in view["pending"]


def test_non_eu_visa_reason_uses_the_researched_route(db_session):
    mauritius = _place(db_session, "Mauritius", "MU", visa_retirement=40)
    prof = _profile(["US"])
    view = board.criteria_view(db_session, mauritius, prof, [])
    assert view["reasons"]["visa"] == {"code": "visa_level", "v": "hard"}  # 0.40, not the seed bucket


def test_retiree_persona_no_longer_double_counts_visa():
    # The bundled registry (migration 0029 applies the same edit to a DB-stored copy).
    retiree = next(p for p in criteria.file_registry()["personas"] if p["key"] == "retiree")
    assert retiree["weights"]["visa"] <= 2.0
    assert any(cc.get("mobility") for cc in retiree["custom_criteria"])


def test_climate_is_graded_by_distance():
    # Wanting "warm": mild Portugal is a near miss, temperate Netherlands is not — a flat 0.5 for
    # every mismatch let cool countries tie once visas stopped separating EU destinations.
    assert sl._climate_value("warm", "warm") == 1.0
    assert sl._climate_value("warm", "mild") == 0.6
    assert sl._climate_value("warm", "temperate") == 0.3
    assert sl._climate_value("warm", "cold") == 0.1
    assert sl._climate_value(None, "cold") == 0.5  # no preference → neutral
    assert sl._climate_value("warm", None) == 0.5  # unknown climate → neutral
