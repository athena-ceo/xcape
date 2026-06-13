# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.db.seed import seed


def test_instant_shortlist_from_seed(auth_client, db_session):
    seeded = seed(db_session)
    assert seeded > 0

    search = auth_client.post("/api/v1/searches", json={"title": "Test"})
    assert search.status_code == 201
    sid = search.json()["id"]

    resp = auth_client.post(f"/api/v1/searches/{sid}/shortlist")
    assert resp.status_code == 200
    candidates = resp.json()
    assert 0 < len(candidates) <= 15
    # Scores are present and sorted descending.
    scores = [c["match_score"] for c in candidates]
    assert scores == sorted(scores, reverse=True)


def test_shortlist_reflects_profile_priorities(auth_client, db_session):
    seed(db_session)
    # Leaving for political reasons should rank highly-stable countries near the top.
    auth_client.put(
        "/api/v1/profile",
        json={"reasons_leaving": ["politics", "safety"], "climate_pref": "mild"},
    )
    sid = auth_client.post("/api/v1/searches", json={"title": "T"}).json()["id"]
    candidates = auth_client.post(f"/api/v1/searches/{sid}/shortlist").json()

    assert candidates, "expected a non-empty shortlist"
    # Top candidate carries human-readable match reasons.
    assert isinstance(candidates[0]["match_reasons"], list)
    assert len(candidates[0]["match_reasons"]) >= 1

    places = {p["id"]: p for p in auth_client.get("/api/v1/places?kind=country").json()}
    top = places[candidates[0]["place_id"]]
    assert top["attributes"]["political_stability"] == "high"


def test_candidate_unique_per_search(auth_client, db_session):
    seed(db_session)
    sid = auth_client.post("/api/v1/searches", json={"title": "T"}).json()["id"]
    place_id = auth_client.get("/api/v1/places?kind=country").json()[0]["id"]

    first = auth_client.post(f"/api/v1/searches/{sid}/candidates", json={"place_id": place_id})
    assert first.status_code == 201
    # Re-adding the same place reactivates rather than duplicating.
    second = auth_client.post(f"/api/v1/searches/{sid}/candidates", json={"place_id": place_id})
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
