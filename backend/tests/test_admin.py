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
