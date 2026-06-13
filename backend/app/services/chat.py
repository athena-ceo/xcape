# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Scoped relocation chat.

The assistant is limited to the user's profile, candidates, and relocation topics.
Questions about political stability / trends of target countries ARE in scope (a core
motivation per the requirements); unrelated requests are politely declined.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.chat import ChatMessage
from app.models.search import Search
from app.models.user import User
from app.services import ai_client

SYSTEM_PROMPT = (
    "You are xCape's relocation assistant. Help the user choose a country/region/city to "
    "move to, using their profile and shortlist. You MAY discuss political stability, "
    "governance trends, safety, prejudice and social climate of candidate destinations — "
    "these are legitimate relocation concerns. Politely decline anything unrelated to the "
    "relocation search. Answer in the user's locale. Format your answer in Markdown: short "
    "paragraphs, and bullet lists or bold labels where they aid readability."
)


def reply(db: Session, user: User, search: Search, message: str) -> ChatMessage:
    db.add(ChatMessage(search_id=search.id, role="user", content=message))
    db.commit()

    try:
        answer = ai_client.respond(
            message,
            web_search=True,
            system=SYSTEM_PROMPT,
            kind="chat",
            db=db,
            user_id=user.id,
        )
    except ai_client.AIUnavailable:
        answer = (
            "Le service IA n'est pas encore configuré (clé OpenAI manquante)."
            if user.locale == "fr"
            else "The AI service is not configured yet (missing OpenAI key)."
        )

    msg = ChatMessage(search_id=search.id, role="assistant", content=answer)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg
