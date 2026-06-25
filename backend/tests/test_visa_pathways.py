# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.models.custom_eval import PlaceCustomEval
from app.models.place import Place
from app.models.profile import Profile
from app.models.user import User
from app.services import ai_client, visa_pathways

_PATHWAY = {
    "exists": True, "difficulty": 70, "income_eur": 24000, "investment_eur": None,
    "pr_years": 5, "citizenship_years": 10, "min_stay_days": 183, "program_name": "Pensionado",
    "requirements_fr": ["casier vierge", "assurance santé"],
    "requirements_en": ["clean record", "health insurance"],
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


def test_relevant_categories_heritage_right_of_return():
    israel = Place(kind="country", name="Israel", iso_code="IL")
    france = Place(kind="country", name="France", iso_code="FR")
    prof = Profile(user=User(heritages=["jewish"]))
    # Jewish heritage surfaces the ancestry/heritage route for Israel (Law of Return)…
    assert "ancestry" in visa_pathways.relevant_categories(prof, israel)
    # …and for the other broad Jewish-heritage countries (Germany / Spain / Portugal)…
    assert "ancestry" in visa_pathways.relevant_categories(
        prof, Place(kind="country", name="Germany", iso_code="DE"))
    # …but not for an unrelated country, nor when no heritage is declared.
    assert "ancestry" not in visa_pathways.relevant_categories(prof, france)
    assert "ancestry" not in visa_pathways.relevant_categories(
        Profile(user=User(heritages=[])), israel)


def test_residency_criteria_score_by_means(db_session):
    """The finder, as scored criteria: income/investable vs cached visa thresholds, in EUR."""
    from app.services import shortlist
    place = Place(kind="country", name="Investland", iso_code="IV", active=True, attributes={})
    db_session.add(place)
    db_session.commit()
    db_session.add_all([
        PlaceCustomEval(place_id=place.id, key="visa_retirement", label="r", score=70, level="good",
                        summary_fr="", summary_en="", sources=[],
                        meta={"category": "retirement", "exists": True, "income_eur": 24000}),
        PlaceCustomEval(place_id=place.id, key="visa_investment", label="i", score=60, level="ok",
                        summary_fr="", summary_en="", sources=[],
                        meta={"category": "investment", "exists": True, "investment_eur": 250000}),
    ])
    db_session.commit()
    prof = Profile(annual_income=30000, investable_amount=100000, currency="EUR")
    vals = shortlist.residency_values(db_session, [place.id], prof)[place.id]
    assert vals["residency_income"] == 1.0      # 30k ≥ 24k threshold → you clear it
    assert vals["residency_investment"] == 0.5  # 100k < 250k → a route exists but out of reach
    # Neither figure set → criteria stay dormant (no entry at all).
    assert shortlist.residency_values(db_session, [place.id], Profile(currency="EUR")) == {}


def test_heritage_country_maps():
    assert visa_pathways.heritage_countries(["jewish"]) == {"IL", "DE", "ES", "PT"}
    assert visa_pathways.heritage_countries([]) == set()
    # Only the strong/open route boosts the visa-ease score.
    assert visa_pathways.heritage_visa_boost_countries(["jewish"]) == {"IL"}


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
    # Bilingual requirement bullets are stored; the payload carries both arrays AND a single
    # `requirements` resolved to the requested language (so either frontend contract works).
    assert ev.meta["requirements_fr"] == ["casier vierge", "assurance santé"]
    assert ev.meta["requirements_en"] == ["clean record", "health insurance"]
    assert visa_pathways.pathway_payload(ev)["requirements_fr"][0] == "casier vierge"
    assert visa_pathways.pathway_payload(ev)["requirements_en"][0] == "clean record"
    assert visa_pathways.pathway_payload(ev, "fr")["requirements"] == ["casier vierge", "assurance santé"]
    assert visa_pathways.pathway_payload(ev, "en")["requirements"] == ["clean record", "health insurance"]
    # Minimum-stay and program name are carried through to the payload.
    assert ev.meta["min_stay_days"] == 183 and ev.meta["program_name"] == "Pensionado"
    payload = visa_pathways.pathway_payload(ev, "en")
    assert payload["min_stay_days"] == 183 and payload["program_name"] == "Pensionado"
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


def _invest_row(db_session, name, iso, *, threshold, difficulty, exists=True) -> Place:
    p = Place(kind="country", name=name, iso_code=iso, active=True, attributes={})
    db_session.add(p)
    db_session.commit()
    db_session.add(PlaceCustomEval(
        place_id=p.id, key="visa_investment", label="Investment", score=difficulty,
        level="good", summary_fr="fr", summary_en="en", sources=[],
        meta={"category": "investment", "exists": exists, "difficulty": difficulty,
              "investment_eur": threshold, "min_stay_days": 0, "program_name": "Golden Visa"},
    ))
    db_session.commit()
    return p


def test_finder_filters_by_amount_and_ranks(db_session):
    cheap = _invest_row(db_session, "Cheapland", "CH", threshold=250000, difficulty=60)
    _invest_row(db_session, "Pricyland", "PR", threshold=600000, difficulty=80)
    _invest_row(db_session, "Noland", "NO", threshold=100000, difficulty=50, exists=False)

    # €300k clears only the €250k program (and the non-existent route is excluded).
    out = visa_pathways.finder(db_session, 300000, "invest", currency="EUR", rate=1.0)
    assert [r["place_id"] for r in out] == [cheap.id]
    assert out[0]["investment"] == 250000 and out[0]["program_name"] == "Golden Visa"

    # €700k clears both — ranked easiest-first (difficulty desc): Pricyland (80) before Cheapland (60).
    out2 = visa_pathways.finder(db_session, 700000, "invest", currency="EUR", rate=1.0)
    assert [r["name"] for r in out2] == ["Pricyland", "Cheapland"]


def test_finder_endpoint_converts_currency(auth_client, db_session):
    _invest_row(db_session, "Cheapland", "CH", threshold=250000, difficulty=60)
    # 1 EUR = 2 USD would make the €250k threshold $500k; at $300k nothing qualifies, at $600k it does.
    # Default test user currency is EUR (rate 1.0) → €300k qualifies.
    r = auth_client.get("/api/v1/visa/finder?amount=300000&goal=invest&lang=en").json()
    assert r["goal"] == "invest" and len(r["results"]) == 1
    assert r["results"][0]["name"] == "Cheapland"


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
