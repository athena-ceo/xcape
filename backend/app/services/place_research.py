# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""AI-backed enrichment of the place database (cache-first).

These functions are called only on a cache miss or an explicit refresh. Results are
written back to Place / MediaAsset so subsequent reads are instant. Wiring to the
Responses API + structured output is a build-phase task (see plan §5).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.place import Place


def research_place(db: Session, name: str) -> Place | None:
    """Look up a country/region not yet in the DB, structure its attributes, cache it."""
    # TODO(build): ai_client.respond(..., web_search=True) with a structured schema,
    #              then persist a Place(source="ai", freshness_at=now()).
    raise NotImplementedError("AI place research is a build-phase task")


def fetch_media(db: Session, place: Place) -> list:
    """Discover maps/photos/links for a place via web search and cache them."""
    # TODO(build): ai_client.respond(..., web_search=True); persist MediaAsset rows.
    raise NotImplementedError("AI media fetch is a build-phase task")
