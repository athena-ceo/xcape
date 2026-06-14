# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.db.seed import seed
from app.services.comparison import compute_deltas, criterion_delta


def test_register_captures_names_and_defaults_current_country(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "jean@example.com",
            "password": "password123",
            "locale": "fr",
            "first_name": "Jean",
            "last_name": "Dupont",
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["first_name"] == "Jean"
    assert me["last_name"] == "Dupont"
    # Loopback IP in tests -> falls back to locale -> France.
    assert me["current_country"] == "France"


def test_me_tolerates_null_citizenships(auth_client, db_session):
    # Accounts created before the citizenships column have NULL there; /auth/me must
    # still serialize (regression: it used to 500 on the non-optional list field).
    from app.models.user import User

    user = db_session.query(User).filter(User.email == "test@example.com").first()
    user.citizenships = None
    db_session.commit()
    assert auth_client.get("/api/v1/auth/me").status_code == 200


def test_patch_me_updates_current_country(auth_client):
    resp = auth_client.patch("/api/v1/auth/me", json={"current_country": "Belgium"})
    assert resp.status_code == 200
    assert resp.json()["current_country"] == "Belgium"


def test_criterion_delta_direction():
    # Lower cost of living is better for the user.
    assert criterion_delta("cost_of_living", "low", "high") == "better"
    assert criterion_delta("cost_of_living", "high", "low") == "worse"
    assert criterion_delta("safety", "high", "high") == "same"
    # Climate has no inherent direction.
    assert criterion_delta("climate", "warm", "cold") is None


def test_candidates_carry_vs_current_against_france(auth_client, db_session):
    seed(db_session)  # includes France as the default baseline
    sid = auth_client.post("/api/v1/searches", json={"title": "T"}).json()["id"]
    auth_client.post(f"/api/v1/searches/{sid}/shortlist")
    candidates = auth_client.get(f"/api/v1/searches/{sid}/candidates").json()
    assert candidates
    # Every candidate is annotated relative to the current country (France).
    assert all("vs_current" in c for c in candidates)
    assert any(c["vs_current"] for c in candidates)


def test_compute_deltas_skips_unknown_and_climate():
    base = {"cost_of_living": "high", "climate": "mild", "safety": "medium"}
    cand = {"cost_of_living": "low", "climate": "warm", "safety": "high"}
    deltas = compute_deltas(cand, base)
    assert deltas["cost_of_living"] == "better"
    assert deltas["safety"] == "better"
    assert "climate" not in deltas
