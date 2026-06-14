# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.models.place import Place
from app.services.custom_criteria import slugify
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


def test_custom_level_maps_to_value():
    p = _Profile()
    assert _criterion_value("custom_x", {}, p, None, {"custom_x": "good"}) == 1.0
    assert _criterion_value("custom_x", {}, p, None, {"custom_x": "ok"}) == 0.6
    assert _criterion_value("custom_x", {}, p, None, {"custom_x": "bad"}) == 0.3
    # Unknown / not-yet-evaluated → neutral.
    assert _criterion_value("custom_x", {}, p, None, {}) == 0.5


def test_custom_criterion_contributes_to_score():
    place = Place(kind="country", name="X", attributes={"safety": "high"})
    p = _Profile()
    weights = {"safety": 1.0, "custom_x": 1.0}
    good, _ = _score_place(place, weights, p, {"custom_x": "good"})
    bad, _ = _score_place(place, weights, p, {"custom_x": "bad"})
    assert good > bad
