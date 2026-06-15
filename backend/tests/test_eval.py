# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from datetime import datetime, timedelta, timezone

from app.models.custom_eval import PlaceCustomEval
from app.models.place import Place
from app.services import criteria
from app.services.criterion_eval import _is_stale
from app.services.shortlist import _criterion_value, candidate_quality


class _Profile:
    def __init__(self):
        self.minority_groups = []
        self.language_skills = {}
        self.climate_pref = None
        self.user = None


def test_objective_keys_exclude_computed():
    assert "safety" in criteria.objective_keys()
    assert "tax" in criteria.objective_keys()
    for computed in ("visa", "inclusion", "language_ease", "climate", "cost_of_living"):
        assert computed not in criteria.objective_keys()


def test_eval_value_preferred_over_bucket():
    place = Place(kind="country", name="X", attributes={"safety": "low"})  # bucket → 0.15
    p = _Profile()
    # With a cached eval, the numeric score wins over the coarse bucket.
    assert _criterion_value("safety", place.attributes, p, place, {"safety": 0.9}) == 0.9
    # Without an eval, an objective criterion is neutral/provisional — the coarse, optimistic
    # seed bucket is NOT trusted (it's on a far rosier scale than real evals and would let an
    # un-evaluated country leap to the top).
    assert _criterion_value("safety", place.attributes, p, place, {}) == 0.5


def test_objective_value_neutral_when_no_eval_and_no_bucket():
    p = _Profile()
    assert _criterion_value("safety", {}, p, None, {}) == 0.5


def test_candidate_quality_uses_evals():
    place = Place(kind="country", name="X", attributes={})  # seed-sparse country
    p = _Profile()
    q = candidate_quality(place, p, {"safety": 0.9, "tax": 0.2})
    assert q["safety"] == "good"
    assert q["tax"] == "bad"


def test_criteria_view_puts_custom_tier_in_quality(db_session):
    # A custom criterion with a cached eval must surface a colour tier (so the cell shows a
    # value, not a "…" spinner) and must not be reported pending.
    from app.models.custom_eval import PlaceCustomEval
    from app.services import board

    place = Place(kind="country", name="X", attributes={})
    db_session.add(place)
    db_session.commit()
    db_session.add(PlaceCustomEval(place_id=place.id, key="custom_vegan", label="Vegan",
                                   score=88, level="good", summary_en="ok", summary_fr="ok"))
    db_session.commit()
    view = board.criteria_view(db_session, place, None, [{"key": "custom_vegan", "label": "Vegan"}])
    assert view["quality"]["custom_vegan"] == "good"
    assert "custom_vegan" not in view["pending"]


def test_staleness():
    fresh = PlaceCustomEval(freshness_at=datetime.now(timezone.utc))
    old = PlaceCustomEval(freshness_at=datetime.now(timezone.utc) - timedelta(days=60))
    assert not _is_stale(fresh, 30)
    assert _is_stale(old, 30)
    assert not _is_stale(old, 0)  # staleness disabled
