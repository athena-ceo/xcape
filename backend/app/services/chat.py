# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Scoped relocation chat.

The assistant is limited to the user's profile, candidates, and relocation topics. It
is a real multi-turn conversation: each call includes a compact summary of what we know
about the user (profile, citizenships, residence, shortlist) plus the prior turns, so it
never starts fresh. Questions about political stability / trends of target countries ARE
in scope; unrelated requests are politely declined.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.candidate import Candidate
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

_HISTORY_LIMIT = 12  # how many prior turns to include


def _user_context(db: Session, user: User, search: Search) -> str:
    """A compact briefing of everything we know, injected into the system instructions."""
    p = user.profile
    lines = [f"Locale: {user.locale}."]
    name = " ".join(filter(None, [user.first_name, user.last_name]))
    if name:
        lines.append(f"Name: {name}.")
    if user.current_country:
        lines.append(f"Currently lives in (residence): {user.current_country}.")
    if user.citizenships:
        lines.append(f"Citizenship(s): {', '.join(user.citizenships)} (drives visa/mobility).")
    if p:
        if p.household_type:
            lines.append(f"Household: {p.household_type}.")
        if p.reasons_leaving:
            lines.append(f"Reasons for leaving: {', '.join(p.reasons_leaving)}.")
        if p.budget_monthly:
            lines.append(f"Monthly budget: {p.budget_monthly}.")
        if p.tenure:
            lines.append(f"Rent/buy: {p.tenure}.")
        if p.climate_pref:
            lines.append(f"Climate preference: {p.climate_pref}.")
        if p.language_skills:
            known = (p.language_skills or {}).get("known") or []
            if known:
                lines.append(f"Speaks: {', '.join(known)}.")
        if p.criteria_weights:
            lines.append(f"Prioritises: {', '.join(p.criteria_weights.keys())}.")

    cands = (
        db.query(Candidate)
        .filter(Candidate.search_id == search.id, Candidate.status == "active",
                Candidate.selected.is_(True))
        .order_by(Candidate.match_score.desc().nullslast())
        .all()
    )
    picks = [f"{c.place.name} ({round(c.match_score)}%)" for c in cands if c.place and c.match_score]
    if picks:
        lines.append("Shortlist being compared: " + ", ".join(picks) + ".")

    return "What we know about this user:\n" + "\n".join(f"- {x}" for x in lines)


def _build(db: Session, user: User, search: Search) -> tuple[str, list[dict]]:
    """Returns (instructions, input messages) — system briefing + recent conversation."""
    instructions = SYSTEM_PROMPT + "\n\n" + _user_context(db, user, search)
    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.search_id == search.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(_HISTORY_LIMIT)
        .all()
    )
    messages = [{"role": m.role, "content": m.content} for m in reversed(history)]
    return instructions, messages


def reply(db: Session, user: User, search: Search, message: str) -> ChatMessage:
    """Non-streaming reply (used by tests / fallback)."""
    db.add(ChatMessage(search_id=search.id, role="user", content=message))
    db.commit()
    instructions, messages = _build(db, user, search)
    try:
        answer = ai_client.converse(
            messages, system=instructions, web_search=True, kind="chat", db=db, user_id=user.id
        )
    except ai_client.AIUnavailable:
        answer = _unavailable(user)
    msg = ChatMessage(search_id=search.id, role="assistant", content=answer)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def reply_stream(db: Session, user: User, search: Search, message: str) -> Iterator[str]:
    """Streaming reply: yields text deltas, persisting the full answer at the end.

    All ORM reads (save the user turn, build context + history) happen up front while the
    request session is valid. The streaming itself uses a dedicated session, because with
    a StreamingResponse the request-scoped session is torn down before the generator runs.
    """
    db.add(ChatMessage(search_id=search.id, role="user", content=message))
    db.commit()
    instructions, messages = _build(db, user, search)
    search_id, user_id, locale = search.id, user.id, user.locale

    def gen() -> Iterator[str]:
        session = SessionLocal()
        chunks: list[str] = []
        try:
            for delta in ai_client.converse_stream(
                messages, system=instructions, web_search=True, kind="chat",
                db=session, user_id=user_id,
            ):
                chunks.append(delta)
                yield delta
        except ai_client.AIUnavailable:
            fallback = (
                "Le service IA n'est pas encore configuré (clé OpenAI manquante)."
                if locale == "fr"
                else "The AI service is not configured yet (missing OpenAI key)."
            )
            chunks.append(fallback)
            yield fallback
        finally:
            content = "".join(chunks)
            if content:
                session.add(ChatMessage(search_id=search_id, role="assistant", content=content))
                try:
                    session.commit()
                except Exception:
                    session.rollback()
            session.close()

    return gen()


def _unavailable(user: User) -> str:
    return (
        "Le service IA n'est pas encore configuré (clé OpenAI manquante)."
        if user.locale == "fr"
        else "The AI service is not configured yet (missing OpenAI key)."
    )
