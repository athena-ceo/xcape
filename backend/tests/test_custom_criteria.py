# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.models.custom_eval import PlaceCustomEval
from app.models.place import Place
from app.services.criterion_eval import level_from_score, slugify, value_of
from app.services.shortlist import _criterion_value, _score_place


class _Profile:
    def __init__(self):
        self.minority_groups = []
        self.language_skills = {}
        self.climate_pref = None
        self.user = None


def test_slugify_stable_and_prefixed():
    assert slugify("Vegan friendly!") == "custom_vegan_friendly"
    assert slugify("Good surfing") == slugify("  good   SURFING ")


def test_level_derived_from_score():
    assert level_from_score(90) == "good"
    assert level_from_score(55) == "ok"
    assert level_from_score(20) == "bad"
    assert level_from_score(None) == "ok"


def test_value_of_prefers_score_then_level():
    assert value_of(PlaceCustomEval(score=82, level="good")) == 0.82
    # Old rows without a numeric score fall back to the level.
    assert value_of(PlaceCustomEval(score=None, level="good")) == 1.0
    assert value_of(PlaceCustomEval(score=None, level="bad")) == 0.3


def test_custom_value_is_passed_through():
    p = _Profile()
    assert _criterion_value("custom_x", {}, p, None, {"custom_x": 0.82}) == 0.82
    # Not-yet-evaluated (absent from the map) → neutral default.
    assert _criterion_value("custom_x", {}, p, None, {}) == 0.5


def test_custom_criterion_contributes_to_score():
    place = Place(kind="country", name="X", attributes={"safety": "high"})
    p = _Profile()
    weights = {"safety": 1.0, "custom_x": 1.0}
    good, _ = _score_place(place, weights, p, {"custom_x": 0.95})
    bad, _ = _score_place(place, weights, p, {"custom_x": 0.2})
    assert good > bad
