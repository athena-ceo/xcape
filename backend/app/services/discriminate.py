# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""AI-generated discriminating questions that actually move the ranking.

Each question targets one scoring criterion and offers localized answer options, each
carrying an importance weight. Picking an option sets that criterion's weight in the
profile, which re-scores and re-ranks the candidates (see profile update → rescore).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.search import Search
from app.models.user import User
from app.services import ai_client

# Criteria the questions may target — must match the scoring keys.
_CRITERIA = [
    "cost_of_living", "healthcare", "safety", "political_stability",
    "language_ease", "climate", "tax", "visa", "expat_community", "nature", "internet",
]

_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion": {"type": "string", "enum": _CRITERIA},
                    "question": {"type": "string"},
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "weight": {"type": "number"},
                            },
                            "required": ["label", "weight"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["criterion", "question", "options"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}


def generate_questions(db: Session, user: User, search: Search) -> dict:
    candidates = (
        db.query(Candidate)
        .filter(Candidate.search_id == search.id, Candidate.status == "active")
        .all()
    )
    names = [c.place.name for c in candidates if c.place]
    if not names:
        return {"questions": []}

    lang = (user.locale or "fr").lower()
    language = "French" if lang == "fr" else "English"

    system = (
        "You help someone narrow a relocation shortlist by clarifying how much they care "
        "about the criteria that most distinguish their candidate countries. Choose 3-5 "
        f"criteria from this list that differ most across the candidates: {_CRITERIA}. "
        f"For each, write an importance question and 3 answer options IN {language}. Each "
        "option carries a weight: 0 = doesn't matter, 1 = somewhat, 2.5 = very important. "
        "Order options from least to most important."
    )

    return ai_client.respond_json(
        f"Candidate countries: {', '.join(names)}. Generate importance questions to "
        f"discriminate among them.",
        _SCHEMA,
        schema_name="discriminators",
        web_search=False,
        system=system,
        kind="discriminate",
        db=db,
        user_id=user.id,
    )
