# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Map a user's situation (chosen tags + free text) to the criteria that matter.

A small-model structured query: given the criteria catalog (each leaf's key, label, tags
and description) plus the user's selected concern/persona tags and a free-text description,
it returns importance weights for the relevant built-in criteria and proposes a few custom
criteria the catalog doesn't cover. Hybrid by design — works from chips alone, free text
alone, or both.
"""

from __future__ import annotations

from app.core.config import settings
from app.services import ai_client, criteria


def _schema(keys: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "weights": {
                "type": "array",
                "description": "Importance 0-3 for the built-in criteria that matter to this user.",
                "items": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "enum": keys},
                        "weight": {"type": "number", "minimum": 0, "maximum": 3},
                    },
                    "required": ["key", "weight"],
                    "additionalProperties": False,
                },
            },
            "custom": {
                "type": "array",
                "description": "Up to 3 user-specific criteria the catalog doesn't cover.",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["label", "description"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["weights", "custom"],
        "additionalProperties": False,
    }


def suggest(db, user, *, tags: list[str], free_text: str) -> dict:
    """Return {weights: {key: 0-3}, custom: [{label, description}]} for the user's situation.
    Unknown keys are dropped. Empty result on AI unavailable."""
    catalog = [
        {"key": n["key"], "label": n.get("label_en") or n["key"],
         "tags": n.get("tags", []), "about": n.get("ai_description") or n.get("label_en")}
        for n in criteria.nodes() if n.get("kind")
    ]
    valid_keys = {c["key"] for c in catalog}
    tag_labels = [criteria.TAGS.get(t, {}).get("label_en", t) for t in (tags or [])]

    try:
        data = ai_client.respond_json(
            "A person is choosing a country to relocate to. Their stated concerns/persona: "
            f"{', '.join(tag_labels) or '(none)'}. In their own words: "
            f"\"{(free_text or '').strip() or '(none)'}\".\n\n"
            "Here is the catalog of available criteria (key — about):\n"
            + "\n".join(f"- {c['key']} — {c['about']}" for c in catalog)
            + "\n\nChoose which built-in criteria matter to THIS person and how much "
            "(weights 0-3, only include ones that matter), and propose up to 3 custom "
            "criteria (label + one-line description) for needs the catalog doesn't cover. "
            "Use only catalog keys for weights.",
            _schema(list(valid_keys)),
            schema_name="criteria_selection",
            model=settings.openai_chat_model,
            kind="custom",
            db=db,
            user_id=user.id,
        )
    except ai_client.AIUnavailable:
        return {"weights": {}, "custom": []}

    weights = {
        w["key"]: float(w["weight"]) for w in (data.get("weights") or [])
        if w.get("key") in valid_keys
    }
    custom = [
        {"label": c["label"].strip(), "description": (c.get("description") or "").strip()}
        for c in (data.get("custom") or []) if c.get("label", "").strip()
    ][:3]
    return {"weights": weights, "custom": custom}
