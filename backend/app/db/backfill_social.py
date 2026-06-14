# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Backfill the social criteria added in 2026-06 onto existing seeded countries.

For every country Place missing the new attributes, ask the AI (web search + structured
output) to rate social_acceptance (per community), openness, gender_equality, culture and
food, then write them onto Place.attributes. Resumable: commits per place and skips ones
already filled, so it is safe to re-run.

Usage: python -m app.db.backfill_social
Invoked by `./xcape.sh backfill-social <env>`.
"""

from __future__ import annotations

from app.db.session import SessionLocal
from app.models.place import Place
from app.services import ai_client, criteria
from app.services.place_research import _GROUP_LEVELS, _SYSTEM

_NEW_KEYS = ["social_acceptance", "openness", "gender_equality", "culture", "food"]
_LEVELS3 = ["high", "medium", "low"]


def _schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "openness": {"type": "string", "enum": _LEVELS3},
            "gender_equality": {"type": "string", "enum": _LEVELS3},
            "culture": {"type": "string", "enum": _LEVELS3},
            "food": {"type": "string", "enum": _LEVELS3},
            "social_acceptance": {
                "type": "object",
                "properties": {g: {"type": "string", "enum": _GROUP_LEVELS} for g in criteria.community_keys()},
                "required": criteria.community_keys(),
                "additionalProperties": False,
            },
        },
        "required": _NEW_KEYS,
        "additionalProperties": False,
    }


def _needs_backfill(attrs: dict) -> bool:
    return any(k not in attrs for k in _NEW_KEYS)


def main() -> None:
    db = SessionLocal()
    try:
        countries = db.query(Place).filter(Place.kind == "country").all()
        todo = [p for p in countries if _needs_backfill(p.attributes or {})]
        print(f"{len(todo)} / {len(countries)} countries need social backfill.")
        for i, place in enumerate(todo, start=1):
            try:
                data = ai_client.respond_json(
                    f"Assess {place.name} on these social dimensions for someone relocating "
                    f"there. Rate social_acceptance per community (high/mixed/low), and "
                    f"openness, gender_equality, culture, food (high/medium/low).",
                    _schema(),
                    schema_name="social_attrs",
                    web_search=True,
                    system=_SYSTEM,
                    kind="research",
                    db=db,
                )
            except ai_client.AIUnavailable:
                print("AI unavailable — stopping (re-run later to resume).")
                break
            attrs = dict(place.attributes or {})
            for k in _NEW_KEYS:
                if k in data:
                    attrs[k] = data[k]
            place.attributes = attrs
            place.source = place.source or "ai"
            db.commit()
            print(f"[{i}/{len(todo)}] {place.name} ✓")
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
