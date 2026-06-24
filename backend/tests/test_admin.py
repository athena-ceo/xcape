# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.models.user import User


def _make_admin(db, email):
    u = db.query(User).filter(User.email == email).first()
    u.is_admin = True
    db.commit()


def test_admin_can_reset_user_password(auth_client, client, db_session):
    # auth_client is the admin; create a second user to reset.
    _make_admin(db_session, "test@example.com")
    client.post("/api/v1/auth/register", json={"email": "victim@example.com", "password": "oldpassword1"})
    victim = db_session.query(User).filter(User.email == "victim@example.com").first()

    resp = auth_client.post(
        f"/api/v1/admin/users/{victim.id}/reset-password", json={"password": "brandnewpass1"}
    )
    assert resp.status_code == 204

    # Old password no longer works; new one does.
    assert client.post("/api/v1/auth/login",
                       json={"email": "victim@example.com", "password": "oldpassword1"}).status_code == 401
    assert client.post("/api/v1/auth/login",
                       json={"email": "victim@example.com", "password": "brandnewpass1"}).status_code == 200


def test_non_admin_cannot_reset_password(auth_client):
    # auth_client here is a plain (non-admin) user.
    resp = auth_client.post("/api/v1/admin/users/1/reset-password", json={"password": "whatever12"})
    assert resp.status_code == 403


def test_admin_creates_user_then_blocks_duplicate(auth_client, client, db_session):
    _make_admin(db_session, "test@example.com")
    r = auth_client.post("/api/v1/admin/users", json={
        "email": "fresh@example.com", "password": "newpassword1", "first_name": "Fresh"})
    assert r.status_code == 201 and r.json()["email"] == "fresh@example.com"
    # The created account can log in immediately.
    assert client.post("/api/v1/auth/login",
                       json={"email": "fresh@example.com", "password": "newpassword1"}).status_code == 200
    # Duplicate email is rejected (409, not 500).
    dup = auth_client.post("/api/v1/admin/users", json={
        "email": "fresh@example.com", "password": "another1234"})
    assert dup.status_code == 409


def test_admin_disable_blocks_login(auth_client, client, db_session):
    _make_admin(db_session, "test@example.com")
    client.post("/api/v1/auth/register", json={"email": "dis@example.com", "password": "password12"})
    victim = db_session.query(User).filter(User.email == "dis@example.com").first()

    assert auth_client.patch(f"/api/v1/admin/users/{victim.id}/active",
                             json={"is_active": False}).status_code == 204
    # Disabled → login forbidden (403), data intact; re-enable restores access.
    assert client.post("/api/v1/auth/login",
                       json={"email": "dis@example.com", "password": "password12"}).status_code == 403
    assert auth_client.patch(f"/api/v1/admin/users/{victim.id}/active",
                             json={"is_active": True}).status_code == 204
    assert client.post("/api/v1/auth/login",
                       json={"email": "dis@example.com", "password": "password12"}).status_code == 200


def test_admin_delete_user_and_guards(auth_client, client, db_session):
    admin = db_session.query(User).filter(User.email == "test@example.com").first()
    _make_admin(db_session, "test@example.com")
    client.post("/api/v1/auth/register", json={"email": "gone@example.com", "password": "password12"})
    victim = db_session.query(User).filter(User.email == "gone@example.com").first()

    # Cannot delete yourself or the last admin.
    assert auth_client.delete(f"/api/v1/admin/users/{admin.id}").status_code == 400
    # A normal user can be hard-deleted.
    assert auth_client.delete(f"/api/v1/admin/users/{victim.id}").status_code == 204
    assert db_session.query(User).filter(User.email == "gone@example.com").first() is None


def test_admin_users_list_has_status_and_login(auth_client, db_session):
    _make_admin(db_session, "test@example.com")
    rows = auth_client.get("/api/v1/admin/users").json()
    me = next(r for r in rows if r["email"] == "test@example.com")
    assert me["is_active"] is True and "last_login_at" in me and "latest_search" in me


def test_pricing_estimate_cost():
    from app.services import pricing

    # gpt-5: $1.25 in / $10 out per 1M tokens → 1M in + 1M out = 1.25 + 10.
    assert pricing.estimate_cost("gpt-5", 1_000_000, 1_000_000) == 11.25
    # Unknown model falls back to the default rates (1.0 / 3.0).
    assert pricing.estimate_cost("mystery", 1_000_000, 0) == 1.0
    assert pricing.estimate_cost("gpt-5", None, None) == 0.0


def test_admin_users_list_aggregates_token_cost(auth_client, db_session):
    from app.models.ai_log import AIQueryLog

    admin = db_session.query(User).filter(User.email == "test@example.com").first()
    _make_admin(db_session, "test@example.com")
    db_session.add_all([
        AIQueryLog(user_id=admin.id, kind="shortlist", model="gpt-5",
                   tokens_in=1_000_000, tokens_out=1_000_000),
        AIQueryLog(user_id=admin.id, kind="chat", model="gpt-5-mini",
                   tokens_in=1_000_000, tokens_out=0),
    ])
    db_session.commit()

    me = next(r for r in auth_client.get("/api/v1/admin/users").json()
              if r["email"] == "test@example.com")
    assert me["ai_calls"] == 2
    assert me["tokens_in"] == 2_000_000 and me["tokens_out"] == 1_000_000
    # gpt-5 (1.25 + 10) + gpt-5-mini (0.25) = 11.50, each model priced separately.
    assert me["cost_estimate"] == 11.5


def test_ai_log_reports_user_and_summaries(auth_client, db_session):
    from app.models.ai_log import AIQueryLog

    admin = db_session.query(User).filter(User.email == "test@example.com").first()
    _make_admin(db_session, "test@example.com")
    db_session.add(AIQueryLog(
        user_id=admin.id, kind="shortlist", model="gpt-5",
        prompt_summary="retire, warm, EUR4000", result_summary="12 countries; top Portugal"))
    db_session.commit()

    row = auth_client.get("/api/v1/admin/ai-log").json()[0]
    assert row["user_email"] == "test@example.com"
    assert row["prompt_summary"] == "retire, warm, EUR4000"
    assert row["result_summary"] == "12 countries; top Portugal"
