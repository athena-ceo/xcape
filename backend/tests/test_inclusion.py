# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.models.place import Place
from app.services.shortlist import (
    _criterion_value,
    _effective_weights,
    candidate_quality,
    passes_filters,
)


class _Profile:
    """Minimal stand-in for the ORM Profile used by the scorer."""

    def __init__(self, minority_groups=None, filters=None):
        self.minority_groups = minority_groups or []
        self.filters = filters or {}
        self.language_skills = {}
        self.climate_pref = None
        self.reasons_leaving = []
        self.household_type = None
        self.criteria_weights = {}
        self.user = None


WELCOMING = {
    "social_acceptance": {"lgbtq": "high", "jewish": "high", "muslim": "high",
                          "ethnic_minorities": "high", "immigrants": "high"},
    "openness": "high",
}
# Welcoming overall but hostile to one community.
MIXED = {
    "social_acceptance": {"lgbtq": "low", "jewish": "high", "muslim": "high",
                          "ethnic_minorities": "high", "immigrants": "mixed"},
    "openness": "medium",
}


def test_inclusion_uses_worst_group():
    # A user who flagged LGBTQ+ should see the country's LGBTQ+ (low) result dominate,
    # even though every other community is welcomed.
    p = _Profile(minority_groups=["lgbtq", "jewish"])
    assert _criterion_value("inclusion", MIXED, p) == 0.15  # low
    assert _criterion_value("inclusion", WELCOMING, p) == 1.0  # all high


def test_inclusion_missing_group_falls_back_to_openness():
    # No community-specific data → use the country's general openness.
    p = _Profile(minority_groups=["lgbtq"])
    assert _criterion_value("inclusion", {"openness": "high"}, p) == 1.0
    assert _criterion_value("inclusion", {"openness": "low"}, p) == 0.15
    assert _criterion_value("inclusion", {}, p) == 0.5  # no data at all → neutral


def test_inclusion_free_text_community_uses_openness():
    # A user-typed community we have no per-country data for is scored via openness, and
    # combines with preset communities under the worst-group rule.
    p = _Profile(minority_groups=["roma people"])
    assert _criterion_value("inclusion", {"openness": "low"}, p) == 0.15
    mixed_plus_free = {**WELCOMING, "openness": "low"}
    p2 = _Profile(minority_groups=["lgbtq", "roma people"])  # lgbtq high, roma→openness low
    assert _criterion_value("inclusion", mixed_plus_free, p2) == 0.15


def test_inclusion_falls_back_to_openness_without_groups():
    p = _Profile(minority_groups=[])
    assert _criterion_value("inclusion", {"openness": "high"}, p) == 1.0
    assert _criterion_value("inclusion", {"openness": "low"}, p) == 0.15


def test_selecting_communities_boosts_inclusion_weight():
    base = _effective_weights(_Profile(minority_groups=[]))["inclusion"]
    boosted = _effective_weights(_Profile(minority_groups=["lgbtq"]))["inclusion"]
    assert boosted > base


def test_inclusion_filter_excludes_unwelcoming():
    p = _Profile(minority_groups=["lgbtq"], filters={"inclusion": True})
    assert passes_filters(Place(kind="country", name="W", attributes=WELCOMING), p)
    assert not passes_filters(Place(kind="country", name="M", attributes=MIXED), p)


def test_gender_culture_food_use_ordinal_scale():
    attrs = {"gender_equality": "high", "culture": "medium", "food": "low"}
    p = _Profile()
    assert _criterion_value("gender_equality", attrs, p) == 1.0
    assert _criterion_value("culture", attrs, p) == 0.6
    assert _criterion_value("food", attrs, p) == 0.3


def test_candidate_quality_includes_new_criteria():
    p = _Profile(minority_groups=["lgbtq"])
    q = candidate_quality(Place(kind="country", name="W", attributes=WELCOMING), p)
    assert q["inclusion"] == "good"
    assert "gender_equality" in q
