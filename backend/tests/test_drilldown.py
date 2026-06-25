# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.models.custom_eval import PlaceCustomEval
from app.models.place import Place
from app.services import ai_client


def _country(db_session) -> Place:
    place = Place(kind="country", name="Testland", iso_code="TL",
                  attributes={"cost_of_living": "low", "climate": "temperate",
                              "safety": "high", "culture": "high"})
    db_session.add(place)
    db_session.commit()
    return place


def test_detail_marks_pending_without_ai(auth_client, db_session, monkeypatch):
    """GET /detail assembles from caches only — no AI call — and flags each criterion."""
    monkeypatch.setattr(ai_client, "respond_json",
                        lambda *a, **k: (_ for _ in ()).throw(ai_client.AIUnavailable("off")))
    place = _country(db_session)

    rows = {r["key"]: r for r in auth_client.get(f"/api/v1/places/{place.id}/detail?lang=en").json()["criteria"]}
    # Objective with no eval: pending, no fabricated score.
    assert rows["safety"]["pending"] is True and rows["safety"]["score"] is None
    # Computed: deterministic score shown now, text pending.
    assert rows["cost_of_living"]["score"] is not None and rows["cost_of_living"]["pending"] is True
    # Proximity is synthesised, never pending.
    assert rows["proximity"]["pending"] is False


def test_generate_fills_in_order_routes_and_caches(auth_client, db_session, monkeypatch):
    """POST /detail/generate fills only `limit` pending keys in order, routes objective→evals
    and computed→criteria_detail, and is cache-first (no repeat AI calls)."""
    calls = {"n": 0}

    def fake_respond_json(*args, schema_name=None, **kwargs):
        calls["n"] += 1
        if schema_name in ("criterion_eval", "criterion_eval_trend"):
            out = {"score": 80, "summary_fr": "ok fr", "summary_en": "ok en", "sources": []}
            if schema_name == "criterion_eval_trend":  # safety uses the trend lens now
                out.update(level="moderate", trend="stable", window="2023–2025",
                           metric_fr="base fr", metric_en="basis en")
            return out
        return {"summary_fr": "détail fr", "summary_en": "detail en", "sources": ["https://x.test"]}

    monkeypatch.setattr(ai_client, "respond_json", fake_respond_json)
    place = _country(db_session)

    # limit=1, computed first → only cost_of_living generated; safety stays pending.
    r1 = auth_client.post(f"/api/v1/places/{place.id}/detail/generate?lang=en",
                          json={"keys": ["cost_of_living", "safety"], "limit": 1}).json()
    rows = {r["key"]: r for r in r1["criteria"]}
    assert rows["cost_of_living"]["pending"] is False and rows["cost_of_living"]["summary"] == "detail en"
    assert rows["safety"]["pending"] is True
    assert calls["n"] == 1

    # Next call fills safety (objective → eval cache).
    r2 = auth_client.post(f"/api/v1/places/{place.id}/detail/generate?lang=en",
                          json={"keys": ["cost_of_living", "safety"], "limit": 2}).json()
    rows = {r["key"]: r for r in r2["criteria"]}
    assert rows["safety"]["pending"] is False and rows["safety"]["score"] == 80
    # Trend `metric` is resolved to the requested language (stored bilingual in meta).
    assert rows["safety"]["meta"]["metric"] == "basis en"
    assert "metric_fr" not in rows["safety"]["meta"]
    # Only safety was generated (cost_of_living already cached) → one more AI call total.
    assert calls["n"] == 2

    # Routing: computed text in place.criteria_detail, objective in place_custom_evals.
    db_session.refresh(place)
    assert "cost_of_living" in (place.criteria_detail or {})
    assert db_session.query(PlaceCustomEval).filter_by(place_id=place.id, key="safety").first() is not None
