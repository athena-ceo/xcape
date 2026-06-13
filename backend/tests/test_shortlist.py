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


def test_shortlist_preselects_top_five(auth_client, db_session):
    seed(db_session)
    sid = auth_client.post("/api/v1/searches", json={"title": "T"}).json()["id"]
    cands = auth_client.post(f"/api/v1/searches/{sid}/shortlist").json()
    selected = [c for c in cands if c["selected"]]
    assert len(selected) == 5
    # The five highest-ranked are the ones pre-selected.
    assert {c["id"] for c in selected} == {c["id"] for c in cands[:5]}


def test_selection_capped_at_five(auth_client, db_session):
    seed(db_session)
    sid = auth_client.post("/api/v1/searches", json={"title": "T"}).json()["id"]
    cands = auth_client.post(f"/api/v1/searches/{sid}/shortlist").json()
    sixth = next(c for c in cands if not c["selected"])
    # Five already selected -> selecting a sixth is rejected.
    resp = auth_client.patch(
        f"/api/v1/searches/{sid}/candidates/{sixth['id']}", json={"selected": True}
    )
    assert resp.status_code == 409
    # Unselect one, then the sixth fits.
    first = cands[0]["id"]
    assert auth_client.patch(
        f"/api/v1/searches/{sid}/candidates/{first}", json={"selected": False}
    ).status_code == 200
    assert auth_client.patch(
        f"/api/v1/searches/{sid}/candidates/{sixth['id']}", json={"selected": True}
    ).status_code == 200


def test_profile_update_rescores_and_preserves_set(auth_client, db_session):
    seed(db_session)
    sid = auth_client.post("/api/v1/searches", json={"title": "T"}).json()["id"]
    before = auth_client.post(f"/api/v1/searches/{sid}/shortlist").json()
    ids_before = {c["id"] for c in before}

    # Editing the profile re-ranks the existing candidates without dropping any.
    auth_client.put("/api/v1/profile", json={"criteria_weights": {"tax": 5.0}})
    after = auth_client.get(f"/api/v1/searches/{sid}/candidates").json()

    assert {c["id"] for c in after} == ids_before  # membership preserved
    assert sum(1 for c in after if c["selected"]) == 5  # selection preserved
    scores = [c["match_score"] for c in after]
    assert scores == sorted(scores, reverse=True)  # re-ranked


def test_score_explanation_breaks_down_and_sums(auth_client, db_session):
    seed(db_session)
    sid = auth_client.post("/api/v1/searches", json={"title": "T"}).json()["id"]
    cands = auth_client.post(f"/api/v1/searches/{sid}/shortlist").json()
    cid = cands[0]["id"]

    exp = auth_client.get(f"/api/v1/searches/{sid}/candidates/{cid}/explanation").json()
    assert exp["rows"], "expected per-criterion rows"
    # Each row carries quality, weight and a contribution; contributions sum to score.
    assert all({"key", "quality", "weight", "contribution"} <= set(r) for r in exp["rows"])
    assert abs(sum(r["contribution"] for r in exp["rows"]) - exp["score"]) < 1.0


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
