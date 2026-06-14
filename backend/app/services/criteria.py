# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Criterion registry — loaded from the single source `app/data/criteria.json`.

The JSON holds a multi-level tree (categories → leaves), cross-cutting tags (personas +
concerns), the reason→tags map, per-leaf value scales, default weights and persona-framed
AI descriptions. Everything else (scoring, evaluation, the board, the report, the frontend
via GET /criteria) reads from here, so built-in and custom criteria are handled the same
way and the content lives in one editable place.

Open-set principle: every dimension here (criteria, tags, categories, personas, reasons,
communities) is an **initial seed**, not a closed universe. New members are added as data
(this JSON, or per-search custom criteria / free-text communities) and are treated as
first-class everywhere — scoring, evaluation, display and filtering iterate the data, never
a hard-coded enum. Code must not assume the set is fixed.

Leaf kinds:
- **objective** — AI-scored 0-100 per country (`ai_description` is the prompt), cached.
- **computed** — user-relative, derived in `shortlist` (cost vs budget, language vs known
  languages, visa vs citizenship, climate vs preference, inclusion vs flagged communities,
  proximity vs current country).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_REGISTRY_FILE = Path(__file__).resolve().parent.parent / "data" / "criteria.json"


@lru_cache(maxsize=1)
def _registry() -> dict:
    return json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))


def raw() -> dict:
    """The whole registry (served to the frontend by GET /criteria)."""
    return _registry()


def nodes() -> list[dict]:
    return _registry()["nodes"]


def _by_key() -> dict[str, dict]:
    return {n["key"]: n for n in nodes()}


def node(key: str) -> dict | None:
    return _by_key().get(key)


def leaves() -> list[dict]:
    """Scored nodes (have a 'kind'), in registry order."""
    return [n for n in nodes() if n.get("kind")]


# --- Ordered key lists (replace the old hard-coded lists in shortlist) ----------------
CRITERIA_KEYS: list[str] = [n["key"] for n in nodes() if n.get("kind")]
OBJECTIVE_KEYS: list[str] = [n["key"] for n in nodes() if n.get("kind") == "objective"]
COMPUTED_KEYS: list[str] = [n["key"] for n in nodes() if n.get("kind") == "computed"]

# --- Lookups derived from the registry ------------------------------------------------
SCALES: dict[str, dict[str, float]] = {
    n["key"]: n["scale"] for n in nodes() if n.get("scale")
}
DEFAULT_WEIGHTS: dict[str, float] = {
    n["key"]: float(n["default_weight"]) for n in nodes()
    if n.get("kind") and n.get("default_weight")
}
LEAF_TAGS: dict[str, list[str]] = {
    n["key"]: n.get("tags", []) for n in nodes() if n.get("kind")
}
REASON_TAGS: dict[str, list[str]] = _registry().get("reason_tags", {})
TAGS: dict[str, dict] = _registry().get("tags", {})
# Communities a user can flag (initial seed; free-text additions are first-class — they
# score via the country's general openness, see shortlist._inclusion_value).
COMMUNITIES: list[dict] = _registry().get("communities", [])
COMMUNITY_KEYS: list[str] = [c["key"] for c in COMMUNITIES]
# Reasons-for-leaving are open too: any key here is a selectable reason and maps to tags.
REASONS: list[str] = list(REASON_TAGS.keys())


def ai_description(key: str) -> str | None:
    n = node(key)
    return n.get("ai_description") if n else None


def value_labels(key: str) -> dict | None:
    n = node(key)
    return n.get("value_labels") if n else None


def label(key: str, lang: str = "fr") -> str:
    n = node(key)
    if not n:
        return key
    return n.get(f"label_{lang}") or n.get("label_en") or key


def tags_for_reasons(reasons: list[str] | None) -> set[str]:
    """The set of tags implied by the user's reasons-for-leaving / priorities."""
    out: set[str] = set()
    for r in (reasons or []):
        out.update(REASON_TAGS.get(r, [r]))
    return out


def definitions(custom_defs: list | None = None) -> dict[str, dict]:
    """The unified set of AI-evaluable criterion definitions for a search — objective
    built-in leaves AND the search's custom criteria — each as {label, description}. The
    single source the evaluation path iterates."""
    defs = {
        n["key"]: {"label": n.get("label_en") or n["key"], "description": n["ai_description"]}
        for n in nodes() if n.get("kind") == "objective"
    }
    for c in (custom_defs or []):
        if c.get("key"):
            defs[c["key"]] = {"label": c.get("label", c["key"]), "description": c.get("description")}
    return defs
