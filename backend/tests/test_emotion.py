# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Emotional layer, first slice: hearts, "your story", postcard + pre-mortem."""

from app.models.emotion import Postcard
from app.models.place import Place
from app.models.user import User
from app.services import ai_client


def _place(db, name="Spain", iso="ES"):
    p = Place(kind="country", name=name, iso_code=iso, active=True, attributes={"climate": "warm"})
    db.add(p)
    db.commit()
    return p


# --- hearts ---------------------------------------------------------------------------------

def test_hearts_round_trip_and_idempotent(auth_client, db_session):
    spain, portugal = _place(db_session), _place(db_session, "Portugal", "PT")
    assert auth_client.put(f"/api/v1/hearts/{spain.id}").status_code == 204
    assert auth_client.put(f"/api/v1/hearts/{spain.id}").status_code == 204  # double tap
    assert auth_client.put(f"/api/v1/hearts/{portugal.id}").status_code == 204

    hearts = auth_client.get("/api/v1/hearts").json()
    assert sorted(h["name"] for h in hearts) == ["Portugal", "Spain"]

    assert auth_client.delete(f"/api/v1/hearts/{spain.id}").status_code == 204
    assert auth_client.delete(f"/api/v1/hearts/{spain.id}").status_code == 204  # already gone
    assert [h["name"] for h in auth_client.get("/api/v1/hearts").json()] == ["Portugal"]
    assert auth_client.put("/api/v1/hearts/999999").status_code == 404


def test_hearts_are_private_and_need_auth(auth_client, client, db_session):
    spain = _place(db_session)
    auth_client.put(f"/api/v1/hearts/{spain.id}")
    client.post("/api/v1/auth/register", json={"email": "other@example.com", "password": "password123"})
    tok = client.post("/api/v1/auth/login",
                      json={"email": "other@example.com", "password": "password123"}).json()["access_token"]
    other = client.get("/api/v1/hearts", headers={"Authorization": f"Bearer {tok}"})
    assert other.status_code == 200 and other.json() == []
    assert client.get("/api/v1/hearts", headers={"Authorization": "Bearer nope"}).status_code == 401


# --- your story ------------------------------------------------------------------------------

def test_story_is_reflected_back_and_saved(auth_client, db_session, monkeypatch):
    seen = {}

    def fake(prompt, schema, **kw):
        seen["prompt"] = prompt
        return {"reflection": "You want sun and calm, close to your grandchildren.",
                "hopes": ["sunny days", "a calmer pace", "grandchildren nearby", "a fourth one"],
                "worries": ["leaving friends"], "persona": "retiree"}
    monkeypatch.setattr(ai_client, "respond_json", fake)

    r = auth_client.post("/api/v1/profile/story",
                         json={"text": "We're retiring and want sun, near the grandkids in Lisbon.", "lang": "en"})

    body = r.json()
    assert r.status_code == 200 and body["reflection"].startswith("You want sun")
    assert body["hopes"] == ["sunny days", "a calmer pace", "grandchildren nearby"]  # capped at 3
    assert body["persona"] == "retiree"
    assert "grandkids in Lisbon" in seen["prompt"]
    prof = auth_client.get("/api/v1/profile").json()
    assert prof["priorities_text"].startswith("We're retiring")
    assert prof["story"]["worries"] == ["leaving friends"]


def test_story_drops_unknown_persona_and_survives_ai_outage(auth_client, db_session, monkeypatch):
    monkeypatch.setattr(ai_client, "respond_json", lambda *a, **k: {
        "reflection": "r", "hopes": [], "worries": [], "persona": "astronaut"})
    assert auth_client.post("/api/v1/profile/story", json={"text": "x"}).json()["persona"] is None

    def down(*a, **k):
        raise ai_client.AIUnavailable("no key")
    monkeypatch.setattr(ai_client, "respond_json", down)
    r = auth_client.post("/api/v1/profile/story", json={"text": "still saved"})
    assert r.status_code == 200 and r.json()["unavailable"] is True
    assert auth_client.get("/api/v1/profile").json()["priorities_text"] == "still saved"


# --- postcard + pre-mortem -----------------------------------------------------------------------

_CARD = {"setting": "Valencia", "postcard": "You wake to the sound of the market…",
         "premortem": [{"title": "Summer heat", "text": "August is long."},
                       {"title": "Paperwork", "text": "Registration takes patience."},
                       {"title": "Missing friends", "text": "Weekly dinners are far away."}]}


def _calls(monkeypatch):
    calls = []

    def fake(prompt, schema, **kw):
        calls.append(prompt)
        return _CARD
    monkeypatch.setattr(ai_client, "respond_json", fake)
    return calls


def test_postcard_is_generated_once_then_cached(auth_client, db_session, monkeypatch):
    calls = _calls(monkeypatch)
    spain = _place(db_session)

    assert auth_client.get(f"/api/v1/places/{spain.id}/postcard?lang=en").json() == {"pending": True}
    made = auth_client.post(f"/api/v1/places/{spain.id}/postcard/generate?lang=en").json()
    assert made["setting"] == "Valencia" and len(made["premortem"]) == 3
    again = auth_client.post(f"/api/v1/places/{spain.id}/postcard/generate?lang=en").json()
    cached = auth_client.get(f"/api/v1/places/{spain.id}/postcard?lang=en").json()
    assert len(calls) == 1 and again["postcard"] == cached["postcard"] and cached["pending"] is False
    # "Another day" re-writes on purpose.
    auth_client.post(f"/api/v1/places/{spain.id}/postcard/generate?lang=en&force=true")
    assert len(calls) == 2
    # Each language is its own postcard.
    assert auth_client.get(f"/api/v1/places/{spain.id}/postcard?lang=fr").json()["pending"] is True


def test_postcard_is_rewritten_when_the_profile_changes(auth_client, db_session, monkeypatch):
    _calls(monkeypatch)
    spain = _place(db_session)
    auth_client.post(f"/api/v1/places/{spain.id}/postcard/generate?lang=en")

    auth_client.put("/api/v1/profile", json={"household_type": "family", "intends_children": True})

    r = auth_client.get(f"/api/v1/places/{spain.id}/postcard?lang=en").json()
    assert r["pending"] is True and r["stale"] is True and r["postcard"]  # old one shown meanwhile


def test_no_postcard_for_the_home_country(auth_client, db_session, monkeypatch):
    calls = _calls(monkeypatch)
    user = db_session.query(User).filter(User.email == "test@example.com").first()
    user.current_country = "France"
    db_session.commit()
    france = _place(db_session, "France", "FR")

    assert auth_client.post(f"/api/v1/places/{france.id}/postcard/generate").json()["home"] is True
    assert calls == [] and db_session.query(Postcard).count() == 0


# --- slice 2: hopes & worries scorecard, heart vs numbers ------------------------------------

_STORY = {"reflection": "r", "hopes": ["a walkable town by the sea"], "worries": ["being lonely"],
          "persona": "retiree",
          "criteria": [
              {"kind": "hope", "label_en": "Walkable seaside towns", "label_fr": "Villes côtières à pied",
               "description": "Walkable small towns on the coast for a retired couple."},
              {"kind": "worry", "label_en": "Easy to make friends", "label_fr": "Se faire des amis",
               "description": "How easily retired newcomers build a social life."},
          ]}


def test_story_hopes_and_worries_become_scored_criteria(auth_client, db_session, monkeypatch):
    monkeypatch.setattr(ai_client, "respond_json", lambda *a, **k: _STORY)
    auth_client.post("/api/v1/profile/story", json={"text": "We want the sea, but fear loneliness."})
    sid = auth_client.post("/api/v1/searches", json={"title": "T"}).json()["id"]

    assert auth_client.post(f"/api/v1/searches/{sid}/apply-story").status_code == 200
    auth_client.post(f"/api/v1/searches/{sid}/apply-story")  # idempotent

    defs = {c["key"]: c for c in auth_client.get(f"/api/v1/searches/{sid}/custom-criteria").json()}
    assert set(defs) == {"custom_walkable_seaside_towns", "custom_easy_to_make_friends"}
    friends = defs["custom_easy_to_make_friends"]
    assert friends["category"] == "story" and friends["weight"] == 1.5
    assert friends["label_fr"] == "Se faire des amis"
    # Persisted to the profile, so a later search carries them too.
    sid2 = auth_client.post("/api/v1/searches", json={"title": "T2"}).json()["id"]
    auth_client.get(f"/api/v1/searches/{sid2}/candidates")  # self-heal merges profile customs
    keys2 = {c["key"] for c in auth_client.get(f"/api/v1/searches/{sid2}/custom-criteria").json()}
    assert "custom_easy_to_make_friends" in keys2


def test_suggested_criteria_are_told_what_the_story_covers(auth_client, db_session, monkeypatch):
    monkeypatch.setattr(ai_client, "respond_json", lambda *a, **k: _STORY)
    auth_client.post("/api/v1/profile/story", json={"text": "The sea, and friends."})
    sid = auth_client.post("/api/v1/searches", json={"title": "T"}).json()["id"]
    auth_client.post(f"/api/v1/searches/{sid}/apply-story")
    seen = {}

    def fake(prompt, schema, **kw):
        seen["prompt"] = prompt
        return {"weights": {}, "custom": []}
    monkeypatch.setattr(ai_client, "respond_json", fake)
    auth_client.post(f"/api/v1/searches/{sid}/suggest-criteria", json={"tags": [], "text": "The sea."})

    assert "ALREADY covered" in seen["prompt"] and "Easy to make friends" in seen["prompt"]


def test_heart_vs_numbers(auth_client, db_session):
    from app.models.candidate import Candidate
    from app.models.search import Search
    user = db_session.query(User).filter(User.email == "test@example.com").first()
    on_board, off_board = _place(db_session), _place(db_session, "Portugal", "PT")
    search = Search(user_id=user.id, title="t")
    db_session.add(search)
    db_session.commit()
    db_session.add(Candidate(search_id=search.id, place_id=on_board.id, selected=True, status="active"))
    db_session.commit()
    assert auth_client.get(f"/api/v1/searches/{search.id}/hearts").json() == []

    auth_client.put(f"/api/v1/hearts/{on_board.id}")
    auth_client.put(f"/api/v1/hearts/{off_board.id}")
    rows = {r["name"]: r for r in auth_client.get(f"/api/v1/searches/{search.id}/hearts").json()}

    assert rows["Spain"]["status"] == "on_board"
    pt = rows["Portugal"]
    assert pt["status"] == "ranked_below" and pt["rank"] and pt["reference"]["name"] == "Spain"
    assert len(pt["gaps"]) <= 2 and "strengths" not in pt
