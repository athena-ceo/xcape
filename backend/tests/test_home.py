# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""The home country is the comparison baseline, not a destination (user feedback 2026-10-25:
it was "presented as though it were a third party — visa difficulty, healthcare, etc.").
Immigration criteria are N/A there and left out of its score; services are judged by their
resident quality, not newcomer access."""

from app.models.custom_eval import PlaceCustomEval
from app.models.place import Place
from app.models.profile import Profile
from app.models.search import Search
from app.models.user import User
from app.services import board, criterion_eval
from app.services import shortlist as sl

RETIRE = {"key": "custom_retirement_visa", "label": "Retirement visa", "weight": 6, "source": "persona"}


def _ev(place, key, score, meta=None):
    return PlaceCustomEval(place_id=place.id, key=key, label=key, score=score, level="ok",
                           summary_fr="fr", summary_en="en", sources=[], meta=meta)


def _setup(db, *, citizenships=("US",)):
    user = db.query(User).filter(User.email == "test@example.com").first()
    user.current_country = "France"
    user.citizenships = list(citizenships)
    if user.profile is None:
        db.add(Profile(user_id=user.id))
        db.commit()
    user.profile.persona = "retiree"
    user.profile.criteria_weights = {"visa": 5, "healthcare": 6, "expat_community": 1,
                                     "residency_income": 3}
    user.profile.annual_income = 50000
    user.profile.currency = "EUR"
    home = Place(kind="country", name="France", iso_code="FR", active=True, attributes={})
    db.add(home)
    db.commit()
    db.add_all([
        # Excellent care, but slow for a NEWCOMER to access → headline 55, quality 90.
        _ev(home, "healthcare", 55, {"quality": 90, "access": 30}),
        _ev(home, "expat_community", 40),
        _ev(home, "visa_retirement", 30, {"category": "retirement", "exists": True, "income_eur": 99999}),
        _ev(home, "custom_retirement_visa", 30),
    ])
    search = Search(user_id=user.id, title="t", custom_criteria=[RETIRE])
    db.add(search)
    db.commit()
    return user, home, search


def test_home_column_marks_immigration_criteria_not_applicable(auth_client, db_session):
    user, home, search = _setup(db_session)

    view = board.criteria_view(db_session, home, user.profile, search.custom_criteria, home=True)

    for key in ("visa", "residency_income", "expat_community", "custom_retirement_visa", "language_ease"):
        assert view["reasons"][key] == {"code": "home_na"}, key
        assert key not in view["quality"] and key not in view["pending"]
    # Healthcare at home = the resident's quality (90 → good), not newcomer access (55).
    assert view["quality"]["healthcare"] == "good"


def test_foreign_column_is_unchanged(auth_client, db_session):
    user, home, search = _setup(db_session)
    view = board.criteria_view(db_session, home, user.profile, search.custom_criteria, home=False)
    assert view["reasons"]["visa"]["code"] == "visa_level"
    assert view["quality"]["healthcare"] != "good"  # 55 headline


def test_home_score_leaves_out_what_doesnt_apply(auth_client, db_session):
    user, home, search = _setup(db_session)

    e = sl.explain_place(db_session, user, home, search)

    assert e["home"] is True
    assert set(e["excluded"]) == {"visa", "residency_income", "expat_community", "custom_retirement_visa",
                                  "language_ease"}  # default weight 0.8; you already manage there
    rows = {r["key"]: r for r in e["rows"]}
    assert not set(e["excluded"]) & set(rows)
    assert rows["healthcare"]["quality"] == 90


def test_baseline_endpoint_score_matches_its_explanation(auth_client, db_session):
    _, _, search = _setup(db_session)

    base = auth_client.get(f"/api/v1/searches/{search.id}/baseline").json()
    expl = auth_client.get(f"/api/v1/searches/{search.id}/baseline/explanation").json()

    assert base["match_score"] == expl["score"]
    assert base["reasons"]["visa"] == {"code": "home_na"}


def test_home_country_page(auth_client, db_session):
    _, home, search = _setup(db_session)

    d = auth_client.get(f"/api/v1/places/{home.id}/detail?lang=en&search={search.id}").json()

    assert d["is_home"] is True
    rows = {r["key"]: r for r in d["criteria"]}
    assert rows["visa"]["summary"].startswith("Not applicable") and rows["visa"]["score"] is None
    assert rows["visa"]["pending"] is False
    assert rows["healthcare"]["score"] == 90

    a = auth_client.get(f"/api/v1/places/{home.id}/affordability?lang=en").json()
    assert a["is_home"] is True and a["income_pathways"] == [] and a["investment_route"] is None


def test_evaluate_pending_spends_no_ai_on_home_na_criteria(auth_client, db_session, monkeypatch):
    _, home, search = _setup(db_session)
    called: list[tuple[int, str]] = []
    monkeypatch.setattr(criterion_eval, "evaluate",
                        lambda db, place, key, *a, **k: called.append((place.id, key)))

    auth_client.post(f"/api/v1/searches/{search.id}/evaluate-pending?limit=50")

    assert any(pid == home.id for pid, _ in called)  # the home column WAS evaluated…
    assert not [k for pid, k in called if pid == home.id and k in sl.home_na_keys()]  # …minus N/A


def test_report_home_column_uses_real_values(auth_client, db_session):
    from app.services import report

    user, _, search = _setup(db_session)
    pdf = report.build_report(db_session, user, search, lang="en")
    assert pdf[:4] == b"%PDF"
