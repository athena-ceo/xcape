# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Thin wrapper around the OpenAI Responses API.

Every call should be logged to AIQueryLog by the caller (or via `log_call`). The web
search tool is enabled so the model can pull up-to-date information about places.

This module is intentionally tolerant: if no API key is configured (e.g. local dev
without credentials) the helpers raise AIUnavailable so callers can degrade to the
seed database rather than crash.
"""

from __future__ import annotations

from app.core.config import settings


class AIUnavailable(RuntimeError):
    pass


def _client():
    if not settings.openai_api_key:
        raise AIUnavailable("OPENAI_API_KEY is not configured")
    from openai import OpenAI

    return OpenAI(api_key=settings.openai_api_key)


def respond(prompt: str, *, web_search: bool = False, system: str | None = None) -> str:
    """Single-shot call to the Responses API. Returns the output text.

    TODO: thread structured-output schemas and AIQueryLog recording through here.
    """
    client = _client()
    tools = [{"type": "web_search"}] if web_search else None
    kwargs: dict = {"model": settings.openai_model, "input": prompt}
    if tools:
        kwargs["tools"] = tools
    if system:
        kwargs["instructions"] = system
    resp = client.responses.create(**kwargs)
    return getattr(resp, "output_text", "") or ""


def transcribe_audio(data: bytes, *, filename: str, user_id: int | None = None) -> str:
    """Speech-to-text for voice input. Stub until the audio model is selected."""
    # TODO: client.audio.transcriptions.create(...) with the chosen model.
    raise AIUnavailable("Voice transcription not yet wired")
