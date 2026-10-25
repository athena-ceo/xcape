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


STORY_CATEGORY = "story"  # custom criteria born from the story group as "Your hopes & worries"
STORY_WEIGHT = 1.5        # the user's own words count, without drowning the rest


def _schema(persona_keys: list[str]) -> dict:
    short = {"type": "array", "items": {"type": "string"}, "maxItems": 3}
    return {
        "type": "object",
        "properties": {
            "reflection": {"type": "string"},
            "hopes": short,
            "worries": short,
            "persona": {"type": "string", "enum": persona_keys + [""]},
            "criteria": {
                "type": "array", "maxItems": 6,
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": ["hope", "worry"]},
                        "label_en": {"type": "string"},
                        "label_fr": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["kind", "label_en", "label_fr", "description"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["reflection", "hopes", "worries", "persona", "criteria"],
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
    result: dict = {"reflection": "", "hopes": [], "worries": [], "persona": None, "criteria": []}
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
                f"{menu}\n"
                "- criteria: one per hope and per worry, to score countries on. Phrase each so that "
                "a HIGH score is good for them — a worry like 'being lonely the first year' becomes "
                "'Easy to make friends as a newcomer'. label_en/label_fr: 2-5 words, a column header. "
                "description: one sentence on what to assess in a country, specific to their "
                "situation (e.g. 'for a retired couple'). Skip anything already scored anyway: visa, "
                "cost of living, healthcare, safety, climate, language, and travel time to where "
                "family or friends live ('Near family'). Never give two criteria for the same need "
                "(e.g. 'social life' and 'making friends' are one) — fewer, distinct ones are better.",
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
                "criteria": [
                    {k: (c.get(k) or "").strip() for k in ("kind", "label_en", "label_fr", "description")}
                    for c in (data.get("criteria") or [])
                    if c.get("kind") in ("hope", "worry") and (c.get("label_en") or "").strip()
                ][:6],
            }
        except ai_client.AIUnavailable:
            result["unavailable"] = True
    profile.story = {k: v for k, v in result.items() if k != "unavailable"} if text else None
    db.commit()
    return result


def apply_to_search(db: Session, user: User, search) -> list[str]:
    """Turn the story's hopes and worries into custom criteria on `search` — the "Your hopes &
    worries" scorecard. Labelled in the user's terms, scored by the normal custom-criterion
    pipeline (evaluate-pending), weighted STORY_WEIGHT, and persisted to the profile so every
    later search carries them too. Returns the keys added (existing keys are left alone)."""
    from app.services import criterion_eval, custom_criteria  # avoid module-load cycles

    story = (getattr(user.profile, "story", None) or {}) if user.profile else {}
    defs = list(search.custom_criteria or [])
    have = {c.get("key") for c in defs}
    added: list[dict] = []
    for c in story.get("criteria") or []:
        key = criterion_eval.slugify(c.get("label_en") or "")
        if not key or key in have:
            continue
        d = {"key": key, "label": c["label_en"], "label_en": c["label_en"],
             "label_fr": c.get("label_fr") or c["label_en"], "description": c.get("description"),
             "weight": STORY_WEIGHT, "category": STORY_CATEGORY, "kind": c.get("kind")}
        defs.append(d)
        added.append(d)
        have.add(key)
    if added:
        search.custom_criteria = defs
        search.criteria_set = list({*(search.criteria_set or []), *(d["key"] for d in added)})
        db.commit()
        custom_criteria.persist_to_profile(db, user, added)
    return [d["key"] for d in added]
