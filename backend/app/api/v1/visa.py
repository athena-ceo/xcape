# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Golden-visa finder — rank destinations by an amount the user has.

The inverse of the per-country drill-down: instead of "what visas does country X offer?",
it answers "I have €X (to invest, or as annual income) — where could that take me?". Reads the
pre-computed pathway cache only (no AI on the request path); coverage is filled by
`./xcape.sh evaluate-visas`.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import currencies, fx, visa_pathways

router = APIRouter()


@router.get("/finder")
def visa_finder(
    amount: float,
    goal: str = "invest",          # "invest" (lump sum) | "income" (annual passive income)
    lang: str = "en",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Countries whose `goal` pathway the `amount` clears, ranked best-first. `amount` is in the
    user's budgeting currency (converted to the canonical EUR thresholds here); each result's
    money figures come back converted to that currency for display."""
    if goal not in visa_pathways.FINDER_GOALS:
        goal = "invest"
    currency = currencies.effective_currency(db, user)
    rate = fx.eur_rate(currency)  # units of `currency` per 1 EUR
    amount_eur = (amount / rate) if rate else amount
    results = visa_pathways.finder(
        db, amount_eur, goal, currency=currency, rate=rate, lang=lang)
    return {"currency": currency, "goal": goal, "amount": amount, "results": results}
