# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.services import ai_client, criteria_select


class _User:
    id = 1


def test_suggest_filters_unknown_keys_and_parses_custom(monkeypatch):
    def fake_respond_json(*args, **kwargs):
        return {
            "weights": [
                {"key": "safety", "weight": 3},
                {"key": "tax", "weight": 2},
                {"key": "not_a_real_key", "weight": 3},  # dropped
            ],
            "custom": [
                {"label": "Antisemitism risk", "description": "trend of antisemitic incidents"},
                {"label": "", "description": "ignored — no label"},
            ],
        }

    monkeypatch.setattr(ai_client, "respond_json", fake_respond_json)
    out = criteria_select.suggest(None, _User(), tags=["fear"], free_text="worried")
    assert out["weights"] == {"safety": 3.0, "tax": 2.0}  # unknown key filtered
    assert [c["label"] for c in out["custom"]] == ["Antisemitism risk"]


def test_suggest_empty_on_ai_unavailable(monkeypatch):
    def boom(*a, **k):
        raise ai_client.AIUnavailable("no key")

    monkeypatch.setattr(ai_client, "respond_json", boom)
    out = criteria_select.suggest(None, _User(), tags=[], free_text="")
    assert out == {"weights": {}, "custom": []}
