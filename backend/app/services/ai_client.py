# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Wrapper around the OpenAI Responses API (model gpt-5).

Every call is recorded to AIQueryLog (model, kind, token usage, latency) for the admin
dashboard. The web search tool can be enabled per call so the model pulls up-to-date
information about places. Structured output is requested via a JSON schema so callers
get validated dicts instead of free text.

If no API key is configured the helpers raise AIUnavailable so callers can degrade to
the seed database rather than crash.
"""

from __future__ import annotations

import io
import json
import time
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ai_log import AIQueryLog


class AIUnavailable(RuntimeError):
    pass


def _client():
    if not settings.openai_api_key:
        raise AIUnavailable("OPENAI_API_KEY is not configured")
    from openai import OpenAI

    return OpenAI(api_key=settings.openai_api_key)


def _log(
    db: Session | None,
    *,
    user_id: int | None,
    kind: str,
    model: str,
    summary: str | None,
    usage: Any,
    latency_ms: int,
) -> None:
    if db is None:
        return
    try:
        db.add(
            AIQueryLog(
                user_id=user_id,
                kind=kind,
                model=model,
                prompt_summary=(summary or "")[:500] or None,
                tokens_in=getattr(usage, "input_tokens", None),
                tokens_out=getattr(usage, "output_tokens", None),
                latency_ms=latency_ms,
            )
        )
        db.commit()
    except Exception:  # logging must never break the request
        db.rollback()


def _create(kwargs: dict, *, db, user_id, kind, summary):
    client = _client()
    t0 = time.monotonic()
    resp = client.responses.create(**kwargs)
    latency = int((time.monotonic() - t0) * 1000)
    _log(
        db,
        user_id=user_id,
        kind=kind,
        model=settings.openai_model,
        summary=summary,
        usage=getattr(resp, "usage", None),
        latency_ms=latency,
    )
    return resp


def respond(
    prompt: str,
    *,
    web_search: bool = False,
    system: str | None = None,
    kind: str = "chat",
    db: Session | None = None,
    user_id: int | None = None,
) -> str:
    """Single-shot call returning the output text."""
    kwargs: dict = {"model": settings.openai_model, "input": prompt}
    if web_search:
        kwargs["tools"] = [{"type": "web_search"}]
    if system:
        kwargs["instructions"] = system
    resp = _create(kwargs, db=db, user_id=user_id, kind=kind, summary=prompt)
    return getattr(resp, "output_text", "") or ""


def respond_json(
    prompt: str,
    schema: dict,
    *,
    schema_name: str = "result",
    web_search: bool = False,
    system: str | None = None,
    kind: str = "research",
    reasoning_effort: str | None = "low",
    db: Session | None = None,
    user_id: int | None = None,
) -> dict:
    """Call requesting a JSON object matching `schema` (strict). Returns the parsed dict.

    These are factual extraction tasks, so `reasoning_effort` defaults to "low" to keep
    latency reasonable (gpt-5 + web search is otherwise very slow).
    """
    kwargs: dict = {
        "model": settings.openai_model,
        "input": prompt,
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "strict": True,
            }
        },
    }
    if web_search:
        kwargs["tools"] = [{"type": "web_search"}]
    if system:
        kwargs["instructions"] = system
    if reasoning_effort:
        kwargs["reasoning"] = {"effort": reasoning_effort}
    resp = _create(kwargs, db=db, user_id=user_id, kind=kind, summary=prompt)
    text = getattr(resp, "output_text", "") or "{}"
    return json.loads(text)


def converse(
    messages: list[dict],
    *,
    system: str | None = None,
    web_search: bool = False,
    kind: str = "chat",
    db: Session | None = None,
    user_id: int | None = None,
) -> str:
    """Multi-turn call: `messages` is a list of {role, content}. Returns output text."""
    kwargs: dict = {"model": settings.openai_model, "input": messages}
    if web_search:
        kwargs["tools"] = [{"type": "web_search"}]
    if system:
        kwargs["instructions"] = system
    summary = messages[-1]["content"] if messages else ""
    resp = _create(kwargs, db=db, user_id=user_id, kind=kind, summary=summary)
    return getattr(resp, "output_text", "") or ""


def converse_stream(
    messages: list[dict],
    *,
    system: str | None = None,
    web_search: bool = False,
    kind: str = "chat",
    db: Session | None = None,
    user_id: int | None = None,
):
    """Streaming multi-turn call: yields text deltas as they arrive."""
    client = _client()
    kwargs: dict = {"model": settings.openai_model, "input": messages}
    if web_search:
        kwargs["tools"] = [{"type": "web_search"}]
    if system:
        kwargs["instructions"] = system
    t0 = time.monotonic()
    with client.responses.stream(**kwargs) as stream:
        for event in stream:
            if event.type == "response.output_text.delta":
                yield event.delta
        final = stream.get_final_response()
    latency = int((time.monotonic() - t0) * 1000)
    _log(
        db,
        user_id=user_id,
        kind=kind,
        model=settings.openai_model,
        summary=messages[-1]["content"] if messages else "",
        usage=getattr(final, "usage", None),
        latency_ms=latency,
    )


def transcribe_audio(
    data: bytes,
    *,
    filename: str,
    db: Session | None = None,
    user_id: int | None = None,
) -> str:
    """Speech-to-text for voice input."""
    client = _client()
    buf = io.BytesIO(data)
    buf.name = filename
    t0 = time.monotonic()
    result = client.audio.transcriptions.create(
        model=settings.openai_transcribe_model, file=buf
    )
    latency = int((time.monotonic() - t0) * 1000)
    _log(
        db,
        user_id=user_id,
        kind="voice",
        model=settings.openai_transcribe_model,
        summary=f"transcribe {filename}",
        usage=None,
        latency_ms=latency,
    )
    return getattr(result, "text", "") or ""
