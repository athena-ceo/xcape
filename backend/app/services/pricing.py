# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Rough USD cost estimation for AI usage, so the admin dashboard can gauge spend per user.

Token counts are recorded per call in ``ai_query_logs``; this maps them to an approximate dollar
cost using a small, EDITABLE price table (USD per 1,000,000 tokens, input vs output). These are
estimates for budgeting only — update ``MODEL_PRICING`` when provider prices change. Unknown models
fall back to ``_DEFAULT``. Cost is computed on read (never persisted), so a price correction applies
retroactively to the whole log.
"""

from __future__ import annotations

# USD per 1,000,000 tokens — {model: (input, output)}. Approximate; adjust as provider prices move.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-5": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-4o-mini-transcribe": (1.25, 5.00),
}
_DEFAULT = (1.00, 3.00)


def _rates(model: str | None) -> tuple[float, float]:
    return MODEL_PRICING.get(model or "", _DEFAULT)


def estimate_cost(model: str | None, tokens_in: int | None, tokens_out: int | None) -> float:
    """Approximate USD cost of one call from its token counts and model price."""
    in_rate, out_rate = _rates(model)
    return ((tokens_in or 0) * in_rate + (tokens_out or 0) * out_rate) / 1_000_000
