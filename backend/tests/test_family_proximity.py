# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""The family-proximity criterion: score a candidate by door-to-door TRAVEL TIME to the
nearest place the user wants to stay near (their children, etc.), not raw distance."""

from app.models.place import Place
from app.services import criteria, geo
from app.services.shortlist import _criterion_value, _effective_weights


class _User:
    def __init__(self, family_countries=None):
        self.family_countries = family_countries or []
        self.current_country = "France"
        self.citizenships = []


class _Profile:
    """Minimal stand-in for the ORM Profile used by the scorer."""

    def __init__(self, user=None, criteria_weights=None):
        self.user = user
        self.minority_groups = []
        self.filters = {}
        self.language_skills = {}
        self.climate_pref = None
        self.reasons_leaving = []
        self.household_type = None
        self.intends_children = None
        self.persona = None
        self.criteria_weights = criteria_weights or {}


def _place(iso: str) -> Place:
    return Place(name=iso, iso_code=iso, attributes={})


# --- The deterministic travel-time model ----------------------------------------------

def test_travel_time_prefers_the_sensible_mode_and_is_monotonic():
    # A neighbour is reachable far faster than a far-flung country, and time rises with distance.
    near = geo.travel_time_hours("FR", "ES")   # Spain
    mid = geo.travel_time_hours("FR", "BE")    # Belgium (closer)
    far = geo.travel_time_hours("FR", "AU")    # Australia
    assert mid < near < far
    # Long haul is modelled as a connecting flight with the highest cost band.
    est = geo.travel_estimate("FR", "AU")
    assert est["mode"] == "flight_connection" and est["cost_band"] == "high"
    # Unknown centroid → no estimate (criterion then falls back to neutral).
    assert geo.travel_time_hours("FR", "ZZ") is None


# --- The scored criterion -------------------------------------------------------------

def test_no_family_declared_is_neutral():
    # The majority case: nobody named a family location → the criterion sits at neutral 0.5
    # and never affects the ranking.
    p = _Profile(user=_User(family_countries=[]))
    assert _criterion_value("family_proximity", {}, p, _place("PT")) == 0.5
    assert _criterion_value("family_proximity", {}, _Profile(user=None), _place("PT")) == 0.5


def test_same_country_as_family_scores_top():
    p = _Profile(user=_User(family_countries=["ES"]))
    assert _criterion_value("family_proximity", {}, p, _place("ES")) == 1.0


def test_neighbour_of_family_ranks_high_and_far_ranks_low():
    p = _Profile(user=_User(family_countries=["ES"]))  # children in Spain
    near = _criterion_value("family_proximity", {}, p, _place("FR"))   # neighbour
    far = _criterion_value("family_proximity", {}, p, _place("AU"))    # other side of the world
    assert near >= 0.7   # easy-to-reach tier
    assert far == 0.2    # far band floor
    assert near > far


def test_uses_the_nearest_of_several_family_locations():
    # Children in both Australia and Spain; from France the Spanish tie dominates.
    p = _Profile(user=_User(family_countries=["AU", "ES"]))
    assert _criterion_value("family_proximity", {}, p, _place("FR")) >= 0.7


# --- Weight activation ----------------------------------------------------------------

def test_declaring_family_activates_the_weight_but_stays_dormant_otherwise():
    with_family = _effective_weights(_Profile(user=_User(family_countries=["ES"])))
    without = _effective_weights(_Profile(user=_User(family_countries=[])))
    assert with_family.get("family_proximity", 0) > 0
    assert without.get("family_proximity", 0) == 0


def test_explicit_slider_weight_overrides_the_auto_default():
    p = _Profile(user=_User(family_countries=["ES"]), criteria_weights={"family_proximity": 4.0})
    assert _effective_weights(p)["family_proximity"] == 4.0


def test_family_proximity_is_a_registered_computed_criterion():
    assert "family_proximity" in criteria.computed_keys()
    assert "family_proximity" in criteria.criteria_keys()


# --- Column round-trips through the API (schema + migration wiring) --------------------

def test_family_countries_round_trips(auth_client):
    resp = auth_client.patch("/api/v1/auth/me", json={"family_countries": ["ES", "PT"]})
    assert resp.status_code == 200
    assert resp.json()["family_countries"] == ["ES", "PT"]
    assert auth_client.get("/api/v1/auth/me").json()["family_countries"] == ["ES", "PT"]
