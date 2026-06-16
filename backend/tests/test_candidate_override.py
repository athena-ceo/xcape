# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Explicit user overrides (Candidate.override) win over filters + score:
  - adding a country pins it ("in") — it stays on the board even if it violates a hard filter,
    and survives self-heal-on-load and repopulate;
  - removing a country excludes it ("out") — it never re-enters by score/filters and is offered
    back via the excluded bar; restoring clears the override.
"""

from app.models.place import Place


def _places(db_session, easy: int, hard: int) -> dict[str, list[int]]:
    ids: dict[str, list[int]] = {"easy": [], "hard": []}
    for i in range(easy):
        p = Place(kind="country", name=f"Easy{i}", iso_code=f"E{i}", attributes={"visa": "easy"})
        db_session.add(p)
        db_session.flush()
        ids["easy"].append(p.id)
    for i in range(hard):
        p = Place(kind="country", name=f"Hard{i}", iso_code=f"H{i}", attributes={"visa": "hard"})
        db_session.add(p)
        db_session.flush()
        ids["hard"].append(p.id)
    db_session.commit()
    return ids


def test_added_violator_is_pinned_and_survives_reload_and_repopulate(auth_client, db_session):
    """A hard-filter violator the user explicitly adds stays on the board (flagged), even
    across a plain reload (self-heal) and an explicit repopulate."""
    ids = _places(db_session, easy=2, hard=4)
    auth_client.put("/api/v1/profile", json={"filters": {"visa": True}})
    sid = auth_client.post("/api/v1/searches", json={"title": "T"}).json()["id"]
    auth_client.post(f"/api/v1/searches/{sid}/repopulate")  # board = the 2 visa-qualifying

    hard_id = ids["hard"][0]
    added = auth_client.post(f"/api/v1/searches/{sid}/candidates", json={"place_id": hard_id}).json()
    assert added["override"] == "in" and added["selected"] is True

    def board_entry(via_repopulate: bool):
        if via_repopulate:
            auth_client.post(f"/api/v1/searches/{sid}/repopulate")
        cands = auth_client.get(f"/api/v1/searches/{sid}/candidates").json()
        return next(c for c in cands if c["place_id"] == hard_id)

    # Plain reload (self-heal path): the pinned violator must NOT be dropped, and is flagged.
    on_reload = board_entry(via_repopulate=False)
    assert on_reload["selected"] is True and on_reload["override"] == "in"
    assert "visa" in on_reload["filter_violations"]

    # Explicit repopulate: still pinned on the board.
    on_repopulate = board_entry(via_repopulate=True)
    assert on_repopulate["selected"] is True and on_repopulate["override"] == "in"


def test_excluded_country_stays_off_through_repopulate(auth_client, db_session):
    """A country the user removes is excluded ("out") and never re-enters the board, even when
    it qualifies and a board slot is free."""
    _places(db_session, easy=6, hard=0)  # all qualify; board holds 5, 1 in suggestions
    sid = auth_client.post("/api/v1/searches", json={"title": "T"}).json()["id"]
    auth_client.post(f"/api/v1/searches/{sid}/repopulate")

    cands = auth_client.get(f"/api/v1/searches/{sid}/candidates").json()
    victim = next(c for c in cands if c["selected"])
    excluded = auth_client.post(
        f"/api/v1/searches/{sid}/candidates/{victim['id']}/exclude"
    ).json()
    assert excluded["override"] == "out" and excluded["selected"] is False

    # Repopulate fills the board from the remaining eligible — the excluded one stays out.
    auth_client.post(f"/api/v1/searches/{sid}/repopulate")
    after = auth_client.get(f"/api/v1/searches/{sid}/candidates").json()
    me = next(c for c in after if c["id"] == victim["id"])
    assert me["selected"] is False and me["override"] == "out"
    assert sum(1 for c in after if c["selected"]) == 5  # board still full from the others


def test_restore_clears_override_back_to_neutral_pool(auth_client, db_session):
    """Restoring an excluded country clears the override; it returns to the ranked pool."""
    _places(db_session, easy=6, hard=0)
    sid = auth_client.post("/api/v1/searches", json={"title": "T"}).json()["id"]
    auth_client.post(f"/api/v1/searches/{sid}/repopulate")

    cands = auth_client.get(f"/api/v1/searches/{sid}/candidates").json()
    victim = next(c for c in cands if c["selected"])
    auth_client.post(f"/api/v1/searches/{sid}/candidates/{victim['id']}/exclude")
    restored = auth_client.post(
        f"/api/v1/searches/{sid}/candidates/{victim['id']}/restore"
    ).json()
    assert restored["override"] is None

    # Back in the pool: after a repopulate it is eligible again (selected or a suggestion),
    # never stuck in the excluded set.
    auth_client.post(f"/api/v1/searches/{sid}/repopulate")
    after = auth_client.get(f"/api/v1/searches/{sid}/candidates").json()
    me = next(c for c in after if c["id"] == victim["id"])
    assert me["override"] is None
