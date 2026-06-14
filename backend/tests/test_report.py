# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.models.candidate import Candidate
from app.models.place import Place
from app.models.search import Search
from app.models.user import User


def _setup(db):
    user = db.query(User).filter(User.email == "test@example.com").first()
    place = Place(kind="country", name="Spain", iso_code="ES",
                  attributes={"safety": "high", "cost_of_living": "medium", "climate": "warm"})
    db.add(place)
    db.commit()
    search = Search(user_id=user.id, title="t")
    db.add(search)
    db.commit()
    cand = Candidate(search_id=search.id, place_id=place.id, selected=True,
                     match_score=80, per_criterion=place.attributes)
    db.add(cand)
    db.commit()
    return user, search


def test_build_report_produces_pdf(auth_client, db_session):
    from app.services import report

    user, search = _setup(db_session)
    pdf = report.build_report(db_session, user, search)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 800


def test_report_endpoint(auth_client, db_session):
    _, search = _setup(db_session)
    resp = auth_client.get(f"/api/v1/searches/{search.id}/report.pdf")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"
