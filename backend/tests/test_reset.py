# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.models.candidate import Candidate
from app.models.place import Place
from app.models.profile import Profile
from app.models.search import Search
from app.models.user import User


def _seed(db):
    user = db.query(User).filter(User.email == "test@example.com").first()
    db.add(Profile(user_id=user.id, household_type="single"))
    place = Place(kind="country", name="Spain", attributes={"safety": "high"})
    db.add(place)
    db.commit()
    search = Search(user_id=user.id, title="t")
    db.add(search)
    db.commit()
    db.add(Candidate(search_id=search.id, place_id=place.id, selected=True))
    db.commit()
    return user


def test_reset_clears_profile_and_searches(auth_client, db_session):
    user = _seed(db_session)
    resp = auth_client.post("/api/v1/profile/reset")
    assert resp.status_code == 204, resp.text
    db_session.expire_all()
    assert db_session.query(Search).filter(Search.user_id == user.id).count() == 0
    assert db_session.query(Candidate).count() == 0  # cascaded
    assert db_session.query(Profile).filter(Profile.user_id == user.id).count() == 0
    # The account itself survives.
    assert db_session.query(User).filter(User.id == user.id).count() == 1
