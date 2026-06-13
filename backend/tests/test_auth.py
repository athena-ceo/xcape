# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.


def test_register_and_me(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "a@b.com", "password": "password123"},
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "a@b.com"


def test_duplicate_email_returns_409(client):
    payload = {"email": "dup@b.com", "password": "password123"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    assert client.post("/api/v1/auth/register", json=payload).status_code == 409


def test_login_wrong_password(client):
    client.post("/api/v1/auth/register", json={"email": "c@b.com", "password": "password123"})
    resp = client.post("/api/v1/auth/login", json={"email": "c@b.com", "password": "wrong"})
    assert resp.status_code == 401


def test_me_requires_auth(client):
    assert client.get("/api/v1/auth/me").status_code == 401
