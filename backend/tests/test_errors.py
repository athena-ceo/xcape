# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Failures must be visible: the assistant always answers, and every server-side failure
(failed AI call, unanswerable chat turn, unhandled request error) lands in the admin
Errors tab — prod incident 2026-10-25, where questions "returned silently to the prompt"."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.models.ai_log import AIQueryLog
from app.models.app_error import AppError
from app.models.custom_eval import PlaceCustomEval
from app.models.place import Place
from app.models.user import User
from app.services import ai_client, chat_tools, errors
from app.services import chat as chat_service
from app.services.criterion_eval import insert_eval


def _search(auth_client) -> int:
    return auth_client.post("/api/v1/searches", json={"title": "T"}).json()["id"]


def _make_admin(db, email="test@example.com"):
    u = db.query(User).filter(User.email == email).first()
    u.is_admin = True
    db.commit()


class _FailingResponses:
    def create(self, **kwargs):
        raise TimeoutError("model took too long")


class _FailingClient:
    responses = _FailingResponses()

    def with_options(self, **kwargs):
        return self


def _call(name="rebuild_shortlist"):
    return SimpleNamespace(type="function_call", name=name, arguments="{}", call_id="c1")


def test_ai_failure_still_answers_and_is_recorded_once(auth_client, db_session, monkeypatch):
    sid = _search(auth_client)
    monkeypatch.setattr(ai_client, "_client", lambda: _FailingClient())

    r = auth_client.post(f"/api/v1/searches/{sid}/chat", json={"message": "Why not Spain?"})

    assert r.status_code == 200
    assert "technical problem" in r.json()["reply"] or "problème technique" in r.json()["reply"]
    # Both turns are persisted, so a client that lost the connection can re-read the reply.
    thread = auth_client.get(f"/api/v1/searches/{sid}/chat").json()
    assert [m["role"] for m in thread] == ["user", "assistant"]
    # The failed call is in the AI log with its error…
    log = db_session.query(AIQueryLog).one()
    assert log.status == "error" and "TimeoutError" in log.error
    # …and exactly once in the Errors tab (not again by the chat layer).
    rows = db_session.query(AppError).all()
    assert [(e.source, e.error_type) for e in rows] == [("ai", "TimeoutError")]


def test_tool_failure_still_answers_and_is_recorded(auth_client, db_session, monkeypatch):
    sid = _search(auth_client)
    monkeypatch.setattr(ai_client, "create_with_tools",
                        lambda *a, **k: SimpleNamespace(output=[_call()], output_text=""))

    def boom(*a, **k):
        raise ValueError("tool exploded")
    monkeypatch.setattr(chat_tools, "execute", boom)

    r = auth_client.post(f"/api/v1/searches/{sid}/chat", json={"message": "rebuild"})

    assert r.status_code == 200 and r.json()["reply"]
    e = db_session.query(AppError).one()
    assert (e.source, e.error_type, e.path) == ("chat", "ValueError", f"/searches/{sid}/chat")
    assert e.user_id is not None and "tool exploded" in e.detail


def test_exhausted_tool_loop_is_not_reported_as_missing_key(auth_client, db_session, monkeypatch):
    sid = _search(auth_client)
    monkeypatch.setattr(ai_client, "create_with_tools",
                        lambda *a, **k: SimpleNamespace(output=[_call()], output_text=""))
    monkeypatch.setattr(chat_tools, "execute", lambda *a, **k: ({"ok": True}, True))

    r = auth_client.post(f"/api/v1/searches/{sid}/chat", json={"message": "rebuild"})

    body = r.json()
    assert body["changed"] is True
    assert "OpenAI" not in body["reply"]  # the old fallback blamed a missing API key
    assert db_session.query(AppError).one().error_type == "EmptyReply"


def test_unhandled_request_error_is_recorded(auth_client, db_session, monkeypatch):
    sid = _search(auth_client)

    def crash(*a, **k):
        raise KeyError("unexpected")
    monkeypatch.setattr(chat_service, "reply", crash)
    raw = TestClient(app, raise_server_exceptions=False)
    raw.headers.update(auth_client.headers)

    r = raw.post(f"/api/v1/searches/{sid}/chat", json={"message": "hi"})

    assert r.status_code == 500
    e = db_session.query(AppError).one()
    assert (e.source, e.method, e.path) == ("request", "POST", f"/api/v1/searches/{sid}/chat")
    assert e.error_type == "KeyError" and e.user_id is not None


def test_admin_errors_endpoint(auth_client, db_session):
    assert auth_client.get("/api/v1/admin/errors").status_code == 403
    _make_admin(db_session)
    errors.record(source="ai", error_type="APITimeoutError", message="chat · gpt-5-mini: timed out")

    rows = auth_client.get("/api/v1/admin/errors").json()

    assert [(r["source"], r["error_type"]) for r in rows] == [("ai", "APITimeoutError")]


def test_ai_log_reports_status(auth_client, db_session):
    _make_admin(db_session)
    db_session.add_all([
        AIQueryLog(kind="chat", model="m"),  # legacy row (no status) reads as ok
        AIQueryLog(kind="chat", model="m", status="error", error="TimeoutError: slow"),
    ])
    db_session.commit()

    rows = auth_client.get("/api/v1/admin/ai-log").json()

    assert sorted((r["status"], r["error"] or "") for r in rows) == [
        ("error", "TimeoutError: slow"), ("ok", "")]


def test_error_row_survives_without_user(db_session):
    # No FK on user_id: a row about a since-deleted account is still kept.
    errors.record(source="request", error_type="X", message="m", user_id=987654)
    assert db_session.query(AppError).one().user_id == 987654


def test_recording_never_raises(monkeypatch):
    def broken():
        raise RuntimeError("db down")
    monkeypatch.setattr(errors, "_session_factory", broken)
    errors.record(source="ai", error_type="X", message="m")  # must not raise


def test_concurrent_eval_insert_keeps_the_winner(db_session):
    place = Place(kind="country", name="Spain", iso_code="ES", attributes={})
    db_session.add(place)
    db_session.commit()
    first = PlaceCustomEval(place_id=place.id, key="custom_quiet", label="q", score=70, level="good")
    db_session.add(first)
    db_session.commit()

    # A second request finishing its AI call for the same (place, key) must not 500.
    got = insert_eval(db_session, PlaceCustomEval(place_id=place.id, key="custom_quiet",
                                                  label="q", score=40, level="ok"))

    assert got.id == first.id and got.score == 70
    assert db_session.query(PlaceCustomEval).count() == 1
