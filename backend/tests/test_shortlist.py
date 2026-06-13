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
