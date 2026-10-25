# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

""""Why isn't X in my top 5?" — answered from the board's own scores (prod 2026-10-25: a user
couldn't tell why Spain was missing, and the assistant invented a reason)."""

from app.models.candidate import Candidate
from app.models.custom_eval import PlaceCustomEval
from app.models.place import Place
from app.models.profile import Profile
from app.models.search import Search
from app.models.user import User
from app.services import chat_tools
from app.services import shortlist as sl


def _country(db, name, iso, *, safety, healthcare):
    p = Place(kind="country", name=name, iso_code=iso, active=True, attributes={})
    db.add(p)
    db.commit()
    for key, score in (("safety", safety), ("healthcare", healthcare)):
        db.add(PlaceCustomEval(place_id=p.id, key=key, label=key, score=score, level="ok",
                               summary_fr="", summary_en="", sources=[]))
    db.commit()
    return p


def _setup(db):
    user = db.query(User).filter(User.email == "test@example.com").first()
    user.current_country = "France"
    if user.profile is None:
        db.add(Profile(user_id=user.id))
        db.commit()
    user.profile.criteria_weights = {"safety": 1, "healthcare": 3}
    user.profile.filters = {"safety": "ok"}
    home = _country(db, "France", "FR", safety=80, healthcare=95)
    board = [_country(db, f"Board{i}", f"B{i}", safety=80, healthcare=90 - 2 * i) for i in range(5)]
    below = _country(db, "Lowland", "LW", safety=80, healthcare=60)
    brazil = _country(db, "Brazil", "BR", safety=40, healthcare=63)
    search = Search(user_id=user.id, title="t")
    db.add(search)
    db.commit()
    for p in board:
        db.add(Candidate(search_id=search.id, place_id=p.id, selected=True, status="active"))
    db.commit()
    return user, search, home, board, below, brazil


def test_excluded_by_a_filter_names_it_with_values(auth_client, db_session):
    user, search, _, board, _, brazil = _setup(db_session)

    w = sl.why_not(db_session, user, search, brazil)

    assert w["status"] == "excluded"
    assert w["violations"] == [{"key": "safety", "value": 40, "min": "ok", "relax": "filter"}]
    assert w["reference"]["name"] == "Board4"  # the user's "#5": weakest board member


def test_ranked_below_shows_where_it_loses_points(auth_client, db_session):
    user, search, _, board, below, _ = _setup(db_session)

    w = sl.why_not(db_session, user, search, below)

    assert w["status"] == "ranked_below" and not w["violations"]
    assert w["rank"] > 5 and w["total"] == 7  # home is never ranked
    assert w["score"] < w["reference"]["score"]
    gap = w["gaps"][0]
    assert gap["key"] == "healthcare" and gap["points"] > 0
    assert gap["quality"] == 60 and gap["ref_quality"] == 82


def test_on_board_home_and_removed(auth_client, db_session):
    user, search, home, board, below, _ = _setup(db_session)
    assert sl.why_not(db_session, user, search, board[0])["status"] == "on_board"
    assert sl.why_not(db_session, user, search, home)["status"] == "home"

    db_session.add(Candidate(search_id=search.id, place_id=below.id, selected=False,
                             status="active", override="out"))
    db_session.commit()
    assert sl.why_not(db_session, user, search, below)["status"] == "removed"


def test_why_endpoint(auth_client, client, db_session):
    _, search, _, _, _, brazil = _setup(db_session)

    r = auth_client.get(f"/api/v1/searches/{search.id}/why/{brazil.id}")
    assert r.status_code == 200 and r.json()["status"] == "excluded"
    assert auth_client.get(f"/api/v1/searches/{search.id}/why/999999").status_code == 404

    # Someone else's search is not readable.
    client.post("/api/v1/auth/register", json={"email": "other@example.com", "password": "password123"})
    tok = client.post("/api/v1/auth/login",
                      json={"email": "other@example.com", "password": "password123"}).json()["access_token"]
    r = client.get(f"/api/v1/searches/{search.id}/why/{brazil.id}",
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 404


def test_assistant_tools_are_read_only_and_grounded(auth_client, db_session):
    user, search, _, _, _, brazil = _setup(db_session)

    res, changed = chat_tools.execute(db_session, user, search, "explain_country", {"name": "brazil"})
    assert changed is False and res["ok"] and res["status"] == "excluded"
    assert res["violations"][0]["key"] == "safety"

    res, changed = chat_tools.execute(db_session, user, search, "get_ranking", {"limit": 3})
    assert changed is False and len(res["ranking"]) == 3 and res["total"] == 7
    assert res["ranking"][0]["rank"] == 1

    res, _ = chat_tools.execute(db_session, user, search, "explain_country", {"name": "Atlantis"})
    assert res["ok"] is False


def test_filter_advice_never_counts_the_home_country(auth_client, db_session):
    user, search, home, *_ = _setup(db_session)
    user.profile.filters = {"safety": "good"}  # only the 80s pass (home included, at 80)
    db_session.commit()

    advice = sl.filter_advice(db_session, user, search)

    assert advice["qualified"] == 6  # 5 board + Lowland; France (home) is not a candidate
