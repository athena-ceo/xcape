# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.models.search import Search


def test_delete_me_removes_account_and_data(auth_client, db_session):
    """DELETE /auth/me permanently removes the account and cascades its data (the smoke test
    uses this to clean up after itself)."""
    sid = auth_client.post("/api/v1/searches", json={"title": "T"}).json()["id"]
    assert db_session.get(Search, sid) is not None

    r = auth_client.delete("/api/v1/auth/me")
    assert r.status_code == 204
    db_session.expire_all()
    assert db_session.get(Search, sid) is None            # search cascaded away
    assert auth_client.get("/api/v1/auth/me").status_code == 401  # account gone
