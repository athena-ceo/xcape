# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Criterion registry — the single source of truth for what criteria exist.

Phase 1 keeps this fairly flat (a category tag per leaf) while introducing the key
distinction the new scoring needs:

- **objective** leaves get a cached 0-100 AI evaluation per country (see
  `services.criterion_eval`): safety, taxation, healthcare quality, etc. Their
  `ai_description` is what we ask the model to score. This is how we populate the ~190
  countries that have no seed values for these.
- **computed** leaves are user-relative and derived in code from the profile +
  `place.attributes` (visa from citizenship, language from known languages, climate from
  preference, cost from budget, inclusion from the communities the user flagged). These are
  NOT objectively AI-scored.

Phase 2 will grow `category` into a real tree with sub-criteria.
"""

from __future__ import annotations

# key -> {category, ai_description?}. A leaf is "objective" iff it has an ai_description.
LEAVES: dict[str, dict] = {
    # --- objective: AI-scored 0-100 per country, cached and progressively populated ---
    "safety": {
        "category": "safety",
        "ai_description": "Personal safety and low crime for residents (higher = safer).",
    },
    "political_stability": {
        "category": "safety",
        "ai_description": "Political stability and quality of governance (higher = more stable).",
    },
    "tax": {
        "category": "cost",
        "ai_description": "Favourable taxation for residents — overall burden across income, "
        "social and consumption taxes (higher = lighter / more favourable).",
    },
    "healthcare": {
        "category": "health",
        "ai_description": "Quality and accessibility of healthcare for residents.",
    },
    "education": {
        "category": "practical",
        "ai_description": "Quality and accessibility of schools and universities.",
    },
    "expat_community": {
        "category": "society",
        "ai_description": "Size and supportiveness of the international / expat community.",
    },
    "nature": {
        "category": "lifestyle",
        "ai_description": "Access to nature, landscapes and outdoor environment.",
    },
    "internet": {
        "category": "practical",
        "ai_description": "Internet speed and digital connectivity.",
    },
    "culture": {
        "category": "lifestyle",
        "ai_description": "Richness of cultural life — arts, events, heritage, things to do.",
    },
    "food": {
        "category": "lifestyle",
        "ai_description": "Food culture — quality, variety and availability of good food.",
    },
    "gender_equality": {
        "category": "society",
        "ai_description": "Gender equality — legal rights, equal pay, and fair social and "
        "legal treatment and safety for women.",
    },
    # --- computed: user-relative, derived in shortlist (not objectively AI-scored) ---
    "cost_of_living": {"category": "cost"},      # affordability vs the user's budget
    "language_ease": {"category": "practical"},  # vs the user's known languages
    "visa": {"category": "practical"},           # vs the user's citizenship(s)
    "climate": {"category": "lifestyle"},        # vs the user's climate preference
    "inclusion": {"category": "society"},        # vs the communities the user flagged
}

# Objective leaves get an AI evaluation; computed ones never do.
OBJECTIVE_KEYS = [k for k, v in LEAVES.items() if v.get("ai_description")]
COMPUTED_KEYS = [k for k, v in LEAVES.items() if not v.get("ai_description")]


def ai_description(key: str) -> str | None:
    return LEAVES.get(key, {}).get("ai_description")


def definitions(custom_defs: list | None = None) -> dict[str, dict]:
    """The unified set of AI-evaluable criterion definitions for a search — built-in
    objective leaves AND the search's custom criteria — each as {label, description}. This
    is the single source the evaluation path iterates, so built-in and custom criteria are
    evaluated through one code path (they differ only in where the definition comes from)."""
    defs = {
        k: {"label": k.replace("_", " "), "description": v["ai_description"]}
        for k, v in LEAVES.items() if v.get("ai_description")
    }
    for c in (custom_defs or []):
        if c.get("key"):
            defs[c["key"]] = {"label": c.get("label", c["key"]), "description": c.get("description")}
    return defs
