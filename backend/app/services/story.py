# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

""""Your story": the user describes their situation, hopes and worries in their own words, and
the AI reflects it back ("Here's what I heard…"), pulling out up to 3 hopes, 3 worries and the
relocation profile it suggests. The reflection is the emotional hook — being heard; the text
itself still drives criteria selection (criteria_select.suggest) when onboarding finishes.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.profile import Profile
from app.models.user import User
from app.services import ai_client, criteria

MAX_TEXT = 4000


def _schema(persona_keys: list[str]) -> dict:
    short = {"type": "array", "items": {"type": "string"}, "maxItems": 3}
    return {
        "type": "object",
        "properties": {
            "reflection": {"type": "string"},
            "hopes": short,
            "worries": short,
            "persona": {"type": "string", "enum": persona_keys + [""]},
        },
        "required": ["reflection", "hopes", "worries", "persona"],
        "additionalProperties": False,
    }


def reflect(db: Session, user: User, text: str, lang: str) -> dict:
    """Reflect the story back and persist it on the profile (text → priorities_text, the
    reflection → story). Returns {reflection, hopes, worries, persona, unavailable?}."""
    text = (text or "").strip()[:MAX_TEXT]
    lang = "fr" if lang == "fr" else "en"
    profile = user.profile
    if profile is None:
        profile = Profile(user_id=user.id)
        db.add(profile)
    profile.priorities_text = text

    personas = criteria.personas()
    keys = [p["key"] for p in personas]
    result: dict = {"reflection": "", "hopes": [], "worries": [], "persona": None}
    if text:
        menu = "\n".join(f"- {p['key']}: {p.get('blurb_en') or p.get('label_en')}" for p in personas)
        language = "French" if lang == "fr" else "English"
        try:
            data = ai_client.respond_json(
                "Someone is thinking about moving to another country and told us, in their own "
                f"words:\n\"\"\"{text}\"\"\"\n\n"
                f"Write in {language}, addressing them as 'you' "
                + ("(use 'vous')" if lang == "fr" else "") + ":\n"
                "- reflection: 2-3 warm, plain sentences that show you heard them — their situation, "
                "what they hope for, what worries them. Mirror their words; do not advise, judge, "
                "add facts, or name countries they didn't mention.\n"
                "- hopes: up to 3 short phrases (3-6 words) of what they hope to gain.\n"
                "- worries: up to 3 short phrases of what worries them (leaving or arriving).\n"
                "- persona: the ONE relocation profile below that fits best, or \"\" if none clearly does.\n"
                f"{menu}",
                _schema(keys),
                schema_name="story_reflection",
                model=settings.openai_chat_model,
                kind="story",
                db=db,
                user_id=user.id,
            )
            result = {
                "reflection": (data.get("reflection") or "").strip(),
                "hopes": [h.strip() for h in data.get("hopes", []) if h and h.strip()][:3],
                "worries": [w.strip() for w in data.get("worries", []) if w and w.strip()][:3],
                "persona": data.get("persona") if data.get("persona") in keys else None,
            }
        except ai_client.AIUnavailable:
            result["unavailable"] = True
    profile.story = {k: v for k, v in result.items() if k != "unavailable"} if text else None
    db.commit()
    return result
