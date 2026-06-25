# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Backfill the "living abroad" attributes added in 2026-06 onto existing seeded countries.

For every country Place missing `english` (how far a newcomer gets by in English) and/or
`tax_basis` (territorial / worldwide / hybrid taxation of residents), ask the AI (web search +
structured output) and write them onto Place.attributes. Resumable: commits per place and
skips ones already filled, so it is safe to re-run.

Usage: python -m app.db.backfill_living
Invoked by `./xcape.sh backfill-living <env>`.
"""

from __future__ import annotations

from app.db.session import SessionLocal
from app.models.place import Place
from app.services import ai_client
from app.services.place_research import _ENUMS, _SYSTEM

_NEW_KEYS = ["english", "tax_basis"]


def _schema() -> dict:
    return {
        "type": "object",
        "properties": {k: {"type": "string", "enum": _ENUMS[k]} for k in _NEW_KEYS},
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
        print(f"{len(todo)} / {len(countries)} countries need english/tax_basis backfill.")
        for i, place in enumerate(todo, start=1):
            try:
                data = ai_client.respond_json(
                    f"Assess {place.name} for someone relocating there as a foreign resident. "
                    f"Rate english ({_ENUMS['english']}) — how far a newcomer who speaks only "
                    f"English can manage daily life — and tax_basis ({_ENUMS['tax_basis']}) — "
                    f"whether the country taxes a resident's locally-sourced income only "
                    f"(territorial), worldwide income (worldwide), or a mix / special regime "
                    f"(hybrid).",
                    _schema(),
                    schema_name="living_attrs",
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
