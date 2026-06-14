# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Criterion registry — the single, admin-editable source of the criteria tree.

The registry is one JSON document held in the DB (`app_config['criteria']`), seeded from the
bundled `app/data/criteria.json`. It holds a multi-level tree (categories → leaves),
cross-cutting tags (personas + concerns), the reason→tags map, communities, per-leaf value
scales, default weights and persona-framed AI descriptions. Everything else (scoring,
evaluation, the board, the report, the frontend via GET /criteria) reads from here.

Open-set principle: every dimension (criteria, tags, categories, personas, reasons,
communities) is an editable set — admins add / modify members, and **deactivate rather than
delete** them (each carries an `active` flag, default true). The accessors below return only
**active** members (cascading: a node under a deactivated category is also excluded), so a
deactivated member disappears from scoring/evaluation/display/filtering without data loss.
Per-search custom criteria and free-text communities are first-class too.

These accessors are FUNCTIONS (not import-time constants) so admin edits take effect live —
`invalidate()` clears the cache after a save.

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
    """The registry: the DB document if present, else the bundled file (best-effort so it
    works in tests / before the DB is seeded)."""
    try:
        from app.db.session import SessionLocal
        from app.models.app_config import AppConfig

        db = SessionLocal()
        try:
            row = db.get(AppConfig, "criteria")
            if row and row.value:
                return row.value
        finally:
            db.close()
    except Exception:
        pass
    return json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))


def invalidate() -> None:
    """Drop the cache so the next read reflects an admin edit."""
    _registry.cache_clear()


def file_registry() -> dict:
    """The bundled seed registry (used to seed the DB)."""
    return json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))


def _is_active(m: dict) -> bool:
    return m.get("active", True) is not False


def raw() -> dict:
    """The whole registry, unfiltered (admin GET sees inactive members too)."""
    return _registry()


def nodes() -> list[dict]:
    """All nodes, including inactive (for admin/label resolution)."""
    return _registry().get("nodes", [])


def node(key: str) -> dict | None:
    return {n["key"]: n for n in nodes()}.get(key)


def _active_node_keys() -> set[str]:
    """Keys of nodes that are active AND have no deactivated ancestor."""
    by_key = {n["key"]: n for n in nodes()}

    def ok(n: dict) -> bool:
        cur: dict | None = n
        while cur is not None:
            if not _is_active(cur):
                return False
            cur = by_key.get(cur.get("parent")) if cur.get("parent") else None
        return True

    return {n["key"] for n in nodes() if ok(n)}


def active_nodes() -> list[dict]:
    keys = _active_node_keys()
    return [n for n in nodes() if n["key"] in keys]


def leaves() -> list[dict]:
    """Active scored nodes (have a 'kind'), in registry order."""
    return [n for n in active_nodes() if n.get("kind")]


# --- Ordered key lists (active only) --------------------------------------------------
def criteria_keys() -> list[str]:
    return [n["key"] for n in leaves()]


def objective_keys() -> list[str]:
    return [n["key"] for n in leaves() if n.get("kind") == "objective"]


def computed_keys() -> list[str]:
    return [n["key"] for n in leaves() if n.get("kind") == "computed"]


# --- Lookups (active only) ------------------------------------------------------------
def scales() -> dict[str, dict[str, float]]:
    return {n["key"]: n["scale"] for n in leaves() if n.get("scale")}


def default_weights() -> dict[str, float]:
    return {n["key"]: float(n["default_weight"]) for n in leaves() if n.get("default_weight")}


def leaf_tags() -> dict[str, list[str]]:
    return {n["key"]: n.get("tags", []) for n in leaves()}


def tags() -> dict[str, dict]:
    return {k: v for k, v in _registry().get("tags", {}).items() if _is_active(v)}


def reason_tags() -> dict[str, list[str]]:
    return _registry().get("reason_tags", {})


def reasons() -> list[str]:
    return list(reason_tags().keys())


def communities() -> list[dict]:
    """Active communities (initial seed; free-text additions are first-class)."""
    return [c for c in _registry().get("communities", []) if _is_active(c)]


def community_keys() -> list[str]:
    return [c["key"] for c in communities()]


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


def tags_for_reasons(reason_list: list[str] | None) -> set[str]:
    """The set of tags implied by the user's reasons-for-leaving / priorities."""
    rt = reason_tags()
    out: set[str] = set()
    for r in (reason_list or []):
        out.update(rt.get(r, [r]))
    return out


def definitions(custom_defs: list | None = None) -> dict[str, dict]:
    """Active AI-evaluable criterion definitions for a search — objective built-in leaves AND
    the search's custom criteria — each as {label, description}. The single source the
    evaluation path iterates."""
    defs = {
        n["key"]: {"label": n.get("label_en") or n["key"], "description": n["ai_description"]}
        for n in leaves() if n.get("kind") == "objective"
    }
    for c in (custom_defs or []):
        if c.get("key"):
            defs[c["key"]] = {"label": c.get("label", c["key"]), "description": c.get("description")}
    return defs


def public_registry() -> dict:
    """Active-only registry for the frontend (deactivated members don't appear)."""
    keys = _active_node_keys()
    return {
        "tags": tags(),
        "reason_tags": reason_tags(),
        "communities": communities(),
        "nodes": [n for n in nodes() if n["key"] in keys],
    }
