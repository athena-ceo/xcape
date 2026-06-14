# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.services import criteria

_REG = {
    "tags": {"t1": {"label_fr": "T", "label_en": "T", "kind": "concern"},
             "t2": {"label_fr": "X", "label_en": "X", "kind": "concern", "active": False}},
    "reason_tags": {},
    "communities": [{"key": "a", "label_fr": "A", "label_en": "A"},
                    {"key": "b", "label_fr": "B", "label_en": "B", "active": False}],
    "nodes": [
        {"key": "cat", "parent": None, "label_fr": "C", "label_en": "C"},
        {"key": "live", "parent": "cat", "kind": "objective", "ai_description": "x", "label_en": "Live"},
        {"key": "off", "parent": "cat", "kind": "objective", "ai_description": "x", "label_en": "Off", "active": False},
        {"key": "deadcat", "parent": None, "label_en": "Dead", "active": False},
        {"key": "orphan", "parent": "deadcat", "kind": "objective", "ai_description": "x", "label_en": "Orphan"},
    ],
}


def test_active_filtering(monkeypatch):
    monkeypatch.setattr(criteria, "_registry", lambda: _REG)
    keys = criteria.criteria_keys()
    assert "live" in keys
    assert "off" not in keys                 # directly deactivated
    assert "orphan" not in keys              # under a deactivated category
    assert "off" not in criteria.objective_keys()
    assert "b" not in criteria.community_keys() and "a" in criteria.community_keys()
    assert "t2" not in criteria.tags() and "t1" in criteria.tags()
    # The public registry excludes inactive nodes; admin raw() keeps them.
    assert {n["key"] for n in criteria.public_registry()["nodes"]} == {"cat", "live"}
    assert any(n["key"] == "off" for n in criteria.raw()["nodes"])
