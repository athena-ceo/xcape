# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.models.place import Place
from app.services import criteria, geo
from app.services.shortlist import _criterion_value, _effective_weights


class _Profile:
    def __init__(self, reasons=None, current_country=None):
        self.reasons_leaving = reasons or []
        self.household_type = None
        self.intends_children = None
        self.minority_groups = []
        self.criteria_weights = {}
        self.language_skills = {}
        self.climate_pref = None
        self.user = type("U", (), {"current_country": current_country, "citizenships": []})()


# --- registry integrity --------------------------------------------------------------
def test_every_leaf_has_a_category_parent():
    by_key = {n["key"]: n for n in criteria.nodes()}
    for n in criteria.nodes():
        if n.get("kind"):  # leaf
            parent = by_key.get(n["parent"])
            assert parent is not None, f"{n['key']} has no parent"
            assert not parent.get("kind"), f"{n['key']} parent should be a category"


def test_tags_resolve_and_reasons_map_to_tags():
    for tags in criteria.leaf_tags().values():
        for tag in tags:
            assert tag in criteria.tags(), f"unknown tag {tag}"
    assert "fear" in criteria.tags_for_reasons(["discrimination"])
    assert "financial" in criteria.tags_for_reasons(["patrimoine"])


# --- tag-driven weighting (replaces the old reason->criterion table) ------------------
def test_fear_reason_boosts_the_whole_protection_cluster():
    base = _effective_weights(_Profile())
    fear = _effective_weights(_Profile(reasons=["discrimination"]))
    for key in ("inclusion", "gender_equality", "safety", "political_stability"):
        assert fear[key] > base.get(key, 0), key


def test_financial_reason_boosts_the_money_cluster():
    base = _effective_weights(_Profile())
    fin = _effective_weights(_Profile(reasons=["patrimoine"]))
    for key in ("tax", "tax_treaty", "asset_security"):
        assert fin.get(key, 0) > base.get(key, 0), key


# --- proximity -----------------------------------------------------------------------
def test_distance_resolves_iso_and_name():
    assert geo.distance_between("France", "ES") < 1500           # neighbours → near
    assert geo.distance_between("FR", "JP") > 8000               # far
    assert geo.distance_between("France", "ZZ") is None          # unknown → None


def test_proximity_value_bands():
    p = _Profile(current_country="France")
    near = _criterion_value("proximity", {}, p, Place(kind="country", name="Spain", iso_code="ES"))
    far = _criterion_value("proximity", {}, p, Place(kind="country", name="Japan", iso_code="JP"))
    assert near == 1.0
    assert far == 0.2
    # Unknown origin → neutral.
    assert _criterion_value("proximity", {}, _Profile(), Place(kind="country", name="X", iso_code="ES")) == 0.5
