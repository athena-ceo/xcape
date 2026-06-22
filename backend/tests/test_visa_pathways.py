# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.models.place import Place
from app.models.profile import Profile
from app.models.user import User
from app.services import ai_client, visa_pathways

_PATHWAY = {
    "exists": True, "difficulty": 70, "income_eur": 24000, "investment_eur": None,
    "pr_years": 5, "citizenship_years": 10,
    "requirements": ["clean record", "health insurance"],
    "summary_fr": "fr", "summary_en": "en", "sources": ["https://x.test"],
}


def _country(db_session) -> Place:
    p = Place(kind="country", name="Pathwayland", iso_code="PL", attributes={})
    db_session.add(p)
    db_session.commit()
    return p


def test_relevant_categories_persona_ancestry_universal():
    place = Place(kind="country", name="X", iso_code="PL")
    # Retiree with a declared ancestry tie to PL → retirement first, ancestry + universal too.
    prof = Profile(persona="retiree", user=User(ancestry_countries=["PL"]))
    cats = visa_pathways.relevant_categories(prof, place)
    assert cats[0] == "retirement"
    assert "ancestry" in cats and "work" in cats and "family" in cats
    # No persona / no ancestry → just the universal routes.
    assert visa_pathways.relevant_categories(
        Profile(user=User(ancestry_countries=[])), place) == ["work", "family"]
    # Ancestry elsewhere doesn't add the ancestry route for THIS place.
    assert "ancestry" not in visa_pathways.relevant_categories(
        Profile(user=User(ancestry_countries=["IT"])), place)


def test_evaluate_pathway_caches_meta(db_session, monkeypatch):
    calls = {"n": 0}

    def fake(*a, schema_name=None, **k):
        calls["n"] += 1
        assert schema_name == "visa_pathway"
        return _PATHWAY

    monkeypatch.setattr(ai_client, "respond_json", fake)
    place = _country(db_session)
    ev = visa_pathways.evaluate_pathway(db_session, place, "retirement")
    assert ev.key == "visa_retirement" and ev.score == 70
    assert ev.meta["category"] == "retirement" and ev.meta["income_eur"] == 24000
    assert ev.meta["pr_years"] == 5
    # Cache-first: a second call returns the same row without another AI call.
    ev2 = visa_pathways.evaluate_pathway(db_session, place, "retirement")
    assert calls["n"] == 1 and ev2.id == ev.id


def test_nonexistent_pathway_scored_zero(db_session, monkeypatch):
    """If the program doesn't exist, difficulty is forced to 0 regardless of the model's number."""
    monkeypatch.setattr(ai_client, "respond_json", lambda *a, **k: {**_PATHWAY, "exists": False})
    place = _country(db_session)
    ev = visa_pathways.evaluate_pathway(db_session, place, "investment")
    assert ev.score == 0 and ev.meta["exists"] is False


def test_visa_panel_pending_then_filled(auth_client, db_session, monkeypatch):
    place = _country(db_session)
    # Instant panel from cache: relevant categories present and pending, no best pathway yet.
    r = auth_client.get(f"/api/v1/places/{place.id}/visa-pathways?lang=en").json()
    cats = [c["category"] for c in r["categories"]]
    assert "work" in cats and "family" in cats
    assert all(c["pending"] for c in r["categories"]) and r["best"] is None

    # Generate fills the pending categories on-demand. We deliberately do NOT crown a "best"
    # route (eligibility isn't validated), so best stays None.
    monkeypatch.setattr(ai_client, "respond_json", lambda *a, **k: {**_PATHWAY, "difficulty": 60})
    r2 = auth_client.post(f"/api/v1/places/{place.id}/visa-pathways/generate?lang=en",
                          json={"limit": 9}).json()
    assert all(not c["pending"] for c in r2["categories"])
    assert r2["best"] is None
    filled = next(c for c in r2["categories"] if c["category"] == "work")
    assert filled["difficulty"] == 60 and filled["label"]


def test_visa_force_is_admin_only(auth_client, db_session, monkeypatch):
    place = _country(db_session)
    # A regular user cannot force a re-research.
    assert auth_client.post(f"/api/v1/places/{place.id}/visa-pathways/generate?lang=en",
                            json={"force": True, "categories": ["work"]}).status_code == 403

    # As admin, force re-evaluates an already-cached category (the regenerate action).
    u = db_session.query(User).filter(User.email == "test@example.com").first()
    u.is_admin = True
    db_session.commit()
    calls = {"n": 0}

    def fake(*a, **k):
        calls["n"] += 1
        return _PATHWAY

    monkeypatch.setattr(ai_client, "respond_json", fake)
    auth_client.post(f"/api/v1/places/{place.id}/visa-pathways/generate?lang=en",
                     json={"limit": 9})  # caches the pending categories
    before = calls["n"]
    auth_client.post(f"/api/v1/places/{place.id}/visa-pathways/generate?lang=en",
                     json={"force": True, "categories": ["work"], "limit": 9})  # re-runs just work
    assert calls["n"] == before + 1
