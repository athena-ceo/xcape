# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""AI-generated discriminating questions.

Given the current candidate list, ask the model to surface the *key differences*
between them and turn those into a few questions whose answers would meaningfully
narrow (or expand) the shortlist. Bilingual output.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.search import Search
from app.models.user import User
from app.services import ai_client

_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "question_fr": {"type": "string"},
                    "question_en": {"type": "string"},
                    "why_fr": {"type": "string"},
                    "why_en": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["key", "question_fr", "question_en", "why_fr", "why_en", "options"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You help someone narrow a relocation shortlist. Identify what most distinguishes "
    "the candidate countries and ask 3-5 concise questions whose answers would split "
    "the list. Each question needs short answer options. Be specific to these countries."
)


def generate_questions(db: Session, user: User, search: Search) -> dict:
    candidates = (
        db.query(Candidate)
        .filter(Candidate.search_id == search.id, Candidate.status == "active")
        .all()
    )
    names = [c.place.name for c in candidates if c.place]
    if not names:
        return {"questions": []}

    profile = user.profile
    context = f"Candidate countries: {', '.join(names)}."
    if profile:
        context += (
            f" Household: {profile.household_type}. Reasons for leaving: "
            f"{profile.reasons_leaving}. Climate preference: {profile.climate_pref}."
        )

    return ai_client.respond_json(
        context + " Generate discriminating questions to narrow this shortlist.",
        _SCHEMA,
        schema_name="discriminators",
        web_search=True,
        system=_SYSTEM,
        kind="discriminate",
        db=db,
        user_id=user.id,
    )
