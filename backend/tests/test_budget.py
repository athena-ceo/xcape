# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.services.shortlist import _criterion_value


class _Profile:
    def __init__(self, budget=None, household=None):
        self.budget_monthly = budget
        self.household_type = household
        self.climate_pref = None
        self.language_skills = {}
        self.criteria_weights = {}
        self.user = None


def test_cost_falls_back_to_symbolic_without_budget():
    # No budget -> plain scale: low cost is best, high cost worst.
    assert _criterion_value("cost_of_living", {"cost_of_living": "low"}, _Profile()) > \
        _criterion_value("cost_of_living", {"cost_of_living": "high"}, _Profile())


def test_budget_makes_expensive_country_affordable_or_not():
    high = {"cost_of_living": "high"}
    rich = _criterion_value("cost_of_living", high, _Profile(budget=6000, household="single"))
    poor = _criterion_value("cost_of_living", high, _Profile(budget=1000, household="single"))
    assert rich > poor
    assert rich >= 0.9   # 6000 comfortably covers a high-cost single budget
    assert poor <= 0.2   # 1000 does not


def test_household_size_raises_the_bar():
    low = {"cost_of_living": "low"}
    single = _criterion_value("cost_of_living", low, _Profile(budget=1500, household="single"))
    family = _criterion_value("cost_of_living", low, _Profile(budget=1500, household="family"))
    # The same budget stretches less for a family.
    assert family < single


def test_generous_budget_does_not_eliminate_family_in_mid_cost_country():
    """Regression: on a generous €4000 budget a family was scored 0 (effectively eliminated)
    across mid-cost countries because the flat household multiplier inflated the estimate and
    the curve floored to 0. Housing is largely shared, so the score must stay clearly positive."""
    medium = {"cost_of_living": "medium"}
    family = _criterion_value("cost_of_living", medium, _Profile(budget=4000, household="family"))
    assert family > 0.6  # comfortably affordable, not eliminated

    # A genuinely expensive country still reads as a stretch for a family on the same budget,
    # but is not hard-zeroed (the user can weigh the trade-off, not have it silently dropped).
    high = {"cost_of_living": "high"}
    family_high = _criterion_value("cost_of_living", high, _Profile(budget=4000, household="family"))
    assert 0.0 < family_high < family
