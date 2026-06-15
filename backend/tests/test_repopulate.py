# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.db.seed import seed
from app.models.place import Place
from app.models.profile import Profile
from app.services import shortlist as sl


def test_filter_status_pending_then_violation_then_pass():
    """An objective-criterion threshold can't be judged until its AI eval lands (pending),
    then becomes a violation or a pass depending on the value."""
    place = Place(kind="country", name="X", iso_code="XX", attributes={})
    profile = Profile(filters={"safety": "good"})  # safety is AI-scored (objective)

    pending = sl.filter_status(place, profile, evals={}, custom_defs=[])
    assert pending["pending"] == ["safety"] and not pending["violations"]

    low = sl.filter_status(place, profile, evals={"safety": 0.2}, custom_defs=[])
    assert low["violations"] == ["safety"] and not low["pending"]

    high = sl.filter_status(place, profile, evals={"safety": 0.9}, custom_defs=[])
    assert not high["violations"] and not high["pending"]


def test_custom_criterion_min_is_a_filter():
    place = Place(kind="country", name="X", iso_code="XX", attributes={})
    profile = Profile(filters={})
    defs = [{"key": "surfing", "label": "Surfing", "min": 0.7}]

    assert sl.filter_status(place, profile, evals={}, custom_defs=defs)["pending"] == ["surfing"]
    assert sl.filter_status(place, profile, evals={"surfing": 0.3}, custom_defs=defs)["violations"] == ["surfing"]
    assert sl.passes_filters(place, profile, evals={"surfing": 0.9}, custom_defs=defs)


def test_repopulate_excludes_filter_violators_and_advises(auth_client, db_session):
    """Hard filters are exclusionary: violating countries are dropped from the board (not
    kept-and-flagged), and filter-advice reports how many qualify + what to relax."""
    # Controlled pool (no seed): only 2 countries are easy to settle in.
    for i in range(2):
        db_session.add(Place(kind="country", name=f"Easy{i}", iso_code=f"E{i}",
                             attributes={"visa": "easy"}))
    for i in range(6):
        db_session.add(Place(kind="country", name=f"Hard{i}", iso_code=f"H{i}",
                             attributes={"visa": "hard"}))
    db_session.commit()

    auth_client.put("/api/v1/profile", json={"filters": {"visa": True}})
    sid = auth_client.post("/api/v1/searches", json={"title": "T"}).json()["id"]
    resp = auth_client.post(f"/api/v1/searches/{sid}/repopulate")
    assert resp.status_code == 200

    cands = auth_client.get(f"/api/v1/searches/{sid}/candidates").json()
    selected = [c for c in cands if c["selected"]]
    assert len(selected) == 2, "only the 2 visa-qualifying countries appear (violators dropped)"
    assert all("visa" not in c["filter_violations"] for c in selected)

    advice = auth_client.get(f"/api/v1/searches/{sid}/filter-advice").json()
    assert advice["qualified"] == 2
    top = advice["suggestions"][0]
    assert top["key"] == "visa" and top["admits"] == 6  # relaxing visa would admit the 6 hard ones


def test_repopulate_reranks_to_full_board_and_keeps_filters(auth_client, db_session):
    """Repopulate re-ranks to a full board (best matches) and never clears the user's filters."""
    seed(db_session)
    auth_client.put("/api/v1/profile", json={"filters": {"visa": True}})
    sid = auth_client.post("/api/v1/searches", json={"title": "T"}).json()["id"]
    auth_client.post(f"/api/v1/searches/{sid}/shortlist")

    auth_client.post(f"/api/v1/searches/{sid}/repopulate")
    after = auth_client.get(f"/api/v1/searches/{sid}/candidates").json()

    assert sum(1 for c in after if c["selected"]) == 5  # board stays full after re-ranking
    # The filter survives a repopulate (stability).
    assert auth_client.get("/api/v1/profile").json()["filters"] == {"visa": True}
