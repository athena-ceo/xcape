# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.models.custom_eval import PlaceCustomEval
from app.models.place import Place
from app.models.search import Search
from app.models.user import User


def test_detail_includes_custom_criteria(auth_client, db_session):
    """The drill-down detail must list the search's custom criteria (from the eval cache),
    so they appear like the built-ins. AI is unavailable in tests, so the built-in detail is
    empty and we assert the custom entry is appended."""
    user = db_session.query(User).filter(User.email == "test@example.com").first()
    place = Place(kind="country", name="Portugal", attributes={})
    db_session.add(place)
    db_session.commit()
    db_session.add(PlaceCustomEval(place_id=place.id, key="custom_vegan", label="Vegan",
                                   score=88, level="good", summary_fr="Très bon", summary_en="Great"))
    search = Search(user_id=user.id, title="t",
                    custom_criteria=[{"key": "custom_vegan", "label": "Vegan", "weight": 1.0}])
    db_session.add(search)
    db_session.commit()

    resp = auth_client.get(f"/api/v1/places/{place.id}/detail?lang=en&search={search.id}")
    assert resp.status_code == 200, resp.text
    crits = {c["key"]: c for c in resp.json()["criteria"]}
    # Custom criterion: label + score + justification from the eval cache.
    assert crits["custom_vegan"]["label"] == "Vegan"
    assert crits["custom_vegan"]["score"] == 88
    assert crits["custom_vegan"]["summary"] == "Great"
    # An objective leaf with only a coarse seed bucket and no eval/justification must NOT
    # show a fabricated score.
    assert "safety" in crits and crits["safety"]["score"] is None


def test_unjustified_objective_score_is_hidden_and_proximity_justified(db_session):
    from app.models.place import Place
    from app.services import board

    class _Prof:
        def __init__(self):
            self.minority_groups = []
            self.language_skills = {}
            self.climate_pref = None
            self.user = type("U", (), {"current_country": "France", "citizenships": []})()

    place = Place(kind="country", name="Spain", iso_code="ES",
                  attributes={"culture": "high"})  # bucket only, no eval
    db_session.add(place)
    db_session.commit()
    details = {d["key"]: d for d in board.criterion_details(db_session, place, _Prof(), [], "en")}
    assert details["culture"]["score"] is None        # bucket-only → no fabricated number
    assert details["proximity"]["score"] is not None  # distance-justified
    assert "km" in details["proximity"]["summary"].lower()
