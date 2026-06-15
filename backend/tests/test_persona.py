# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.services import criteria
from app.services.shortlist import _effective_weights


class _Profile:
    def __init__(self, persona=None, reasons=None):
        self.persona = persona
        self.reasons_leaving = reasons or []
        self.household_type = None
        self.intends_children = None
        self.minority_groups = []
        self.criteria_weights = {}


def test_persona_for_matches_reasons():
    assert criteria.persona_for(["discrimination"], []) == "safety_community"
    assert criteria.persona_for(["politics"], []) == "political_exile"
    assert criteria.persona_for(["patrimoine"], []) == "asset_protection"
    assert criteria.persona_for(["retirement"], []) == "retiree"
    assert criteria.persona_for(["career"], []) == "professional"
    assert criteria.persona_for(["climate"], []) == "climate_lifestyle"
    # economy implies financial/tax tags → asset_protection (not professional).
    assert criteria.persona_for(["economy"], []) == "asset_protection"


def test_persona_for_falls_back_to_neutral():
    assert criteria.persona_for([], []) == "neutral"
    assert criteria.persona_for(["something_unknown"], []) == "neutral"


def test_persona_weights_profile_drives_effective_weights():
    w = _effective_weights(_Profile(persona="asset_protection"))
    # Persona's critical criteria carry weight…
    assert w.get("tax", 0) >= 2.5 and w.get("asset_security", 0) >= 2.5
    # …and a criterion the persona doesn't list is absent/zero (genuinely unimportant).
    assert w.get("culture", 0) == 0
    assert w.get("inclusion", 0) == 0


def test_no_persona_uses_defaults():
    w = _effective_weights(_Profile(persona=None))
    # Falls back to the flat default profile (e.g. healthcare has a baseline weight).
    assert w.get("healthcare", 0) > 0


def test_public_registry_includes_personas():
    reg = criteria.public_registry()
    assert "personas" in reg
    keys = {p["key"] for p in reg["personas"]}
    assert {"neutral", "safety_community", "retiree"} <= keys


def test_apply_persona_adds_per_community_criteria(auth_client, db_session):
    from app.db.seed import seed
    seed(db_session)
    auth_client.put("/api/v1/profile", json={
        "persona": "safety_community", "minority_groups": ["jewish", "lgbtq"],
    })
    sid = auth_client.post("/api/v1/searches", json={"title": "T"}).json()["id"]
    auth_client.post(f"/api/v1/searches/{sid}/shortlist")
    auth_client.post(f"/api/v1/searches/{sid}/apply-persona")
    customs = auth_client.get(f"/api/v1/searches/{sid}/custom-criteria").json()
    # One per-community tolerance criterion for each flagged community.
    assert len(customs) == 2
    assert all("community" not in c["description"].lower() or "{community}" not in c["description"]
               for c in customs)  # template was substituted


def test_apply_persona_asset_protection_fixed_criteria(auth_client, db_session):
    from app.db.seed import seed
    seed(db_session)
    auth_client.put("/api/v1/profile", json={"persona": "asset_protection"})
    sid = auth_client.post("/api/v1/searches", json={"title": "T"}).json()["id"]
    auth_client.post(f"/api/v1/searches/{sid}/apply-persona")
    customs = auth_client.get(f"/api/v1/searches/{sid}/custom-criteria").json()
    labels = " ".join(c["label"].lower() for c in customs)
    assert len(customs) == 2  # wealth/inheritance tax + banking
    # Labels come through in the user's locale (fr by default here).
    assert ("impôt" in labels or "tax" in labels) and ("banqu" in labels or "bank" in labels)


def test_custom_criteria_persist_across_searches(auth_client, db_session):
    from app.db.seed import seed
    seed(db_session)
    s1 = auth_client.post("/api/v1/searches", json={"title": "A"}).json()["id"]
    auth_client.post(f"/api/v1/searches/{s1}/custom-criteria",
                     json={"label": "IBM lab", "description": "Does it have an IBM lab?"})
    # A brand-new search inherits the user's persistent custom criteria.
    s2 = auth_client.post("/api/v1/searches", json={"title": "B"}).json()["id"]
    customs = auth_client.get(f"/api/v1/searches/{s2}/custom-criteria").json()
    assert any(c["label"] == "IBM lab" for c in customs)


def test_persona_criteria_carry_category_and_not_persisted(auth_client, db_session):
    from app.db.seed import seed
    seed(db_session)
    auth_client.put("/api/v1/profile", json={"persona": "safety_community", "minority_groups": ["jewish"]})
    s1 = auth_client.post("/api/v1/searches", json={"title": "A"}).json()["id"]
    auth_client.post(f"/api/v1/searches/{s1}/apply-persona")
    customs = auth_client.get(f"/api/v1/searches/{s1}/custom-criteria").json()
    persona_c = [c for c in customs if c.get("source") == "persona"]
    assert persona_c and all(c.get("category") == "protection" for c in persona_c)
    # Persona criteria are per-search: a new search does NOT inherit them (no profile persistence).
    s2 = auth_client.post("/api/v1/searches", json={"title": "B"}).json()["id"]
    customs2 = auth_client.get(f"/api/v1/searches/{s2}/custom-criteria").json()
    assert not any(c.get("source") == "persona" for c in customs2)


def test_derive_endpoint(auth_client, db_session):
    r = auth_client.post("/api/v1/persona/derive", json={"reasons": ["discrimination"], "priorities": []})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["key"] == "safety_community"
    assert body["persona"]["weights"]["inclusion"] >= 2
