# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.services.shortlist import _visa_value, free_access


class _User:
    def __init__(self, citizenships, ancestry=None, heritages=None):
        self.citizenships = citizenships
        self.ancestry_countries = ancestry or []
        self.heritages = heritages or []


class _Profile:
    def __init__(self, citizenships, ancestry=None, heritages=None):
        self.user = _User(citizenships, ancestry, heritages)


class _Place:
    def __init__(self, iso):
        self.iso_code = iso


def test_eu_citizen_moves_freely_within_eu():
    spain, attrs = _Place("ES"), {"visa": "easy"}
    assert _visa_value(attrs, _Profile(["FR"]), spain) == 1.0


def test_non_eu_household_is_judged_by_the_countrys_own_route_not_a_flat_penalty():
    # A US citizen settling in Spain goes through Spain's own visas (non-lucrative, D7 in
    # Portugal…): their ease is the country's researched route, not a blanket "hard" (was 0.3).
    spain = _Place("ES")
    assert _visa_value({"visa": "easy"}, _Profile(["US"]), spain) == 1.0  # seed bucket fallback
    assert _visa_value({"visa": "easy"}, _Profile(["US"]), spain, route_ease=0.75) == 0.75


def test_mixed_household_with_an_eu_passport_moves_freely_within_eu():
    # Polish + American couple → Spain: the EU citizen's spouse and children get a derived right
    # of residence (Directive 2004/38/EC). Judging by the MOST restrictive passport scored this
    # "hard" and pushed Spain out of a Spanish-speaking retiree's top 5 (prod, 2026-10-25).
    spain = _Place("ES")
    assert _visa_value({"visa": "hard"}, _Profile(["PL", "US"]), spain, route_ease=0.3) == 1.0
    assert free_access(_Profile(["PL", "US"]), spain) == {"ease": 1.0, "code": "visa_free", "via": "PL"}


def test_eu_passport_gives_nothing_outside_the_free_movement_zone():
    mauritius = _Place("MU")
    assert free_access(_Profile(["PL", "US"]), mauritius) is None
    assert _visa_value({}, _Profile(["PL", "US"]), mauritius, route_ease=0.78) == 0.78


def test_citizen_of_destination_is_trivial():
    usa = _Place("US")
    assert _visa_value({"visa": "hard"}, _Profile(["US"]), usa) == 1.0
    assert _visa_value({"visa": "hard"}, _Profile(["FR", "US"]), usa) == 1.0


def test_ancestry_country_is_near_automatic():
    poland = _Place("PL")
    assert _visa_value({"visa": "hard"}, _Profile(["US"], ancestry=["PL"]), poland) == 1.0


def test_eu_ancestry_counts_as_likely_free_movement_elsewhere_in_the_eu():
    # Polish ancestry → Polish citizenship by descent → free movement to Portugal: likely, but a
    # claim still to be made, so a notch below holding the passport.
    portugal = _Place("PT")
    fa = free_access(_Profile(["US"], ancestry=["PL"]), portugal)
    assert fa == {"ease": 0.85, "code": "visa_descent", "via": "PL"}
    # Non-EU ancestry carries no EU right.
    assert free_access(_Profile(["US"], ancestry=["BR"]), portugal) is None


def test_open_right_of_return_heritage_is_near_automatic():
    israel = _Place("IL")
    assert free_access(_Profile(["US"], heritages=["jewish"]), israel)["code"] == "visa_ancestry"


def test_unknown_citizenship_falls_back_to_route_then_static():
    spain = _Place("ES")
    # 'easy' on the static scale is 1.0; with no citizenship and no research we use that.
    assert _visa_value({"visa": "easy"}, _Profile([]), spain) == 1.0
    assert _visa_value({"visa": "hard"}, _Profile(None), spain) < 1.0
    assert _visa_value({}, _Profile([]), spain) == 0.5  # nothing known → neutral
