# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from datetime import datetime

from sqlalchemy import (
    JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlaceCustomEval(Base):
    """A cached AI evaluation of one place against one user-defined criterion.

    Keyed by (place_id, key) where key is a slug of the criterion phrase, so the same
    criterion evaluated for the same country is reused across users/searches — exactly
    like the shared Place attributes. level is good/ok/bad (good = best for the user).
    """

    __tablename__ = "place_custom_evals"
    __table_args__ = (UniqueConstraint("place_id", "key", name="uq_custom_eval_place_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    place_id: Mapped[int] = mapped_column(
        ForeignKey("places.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(80), index=True)
    label: Mapped[str] = mapped_column(String(160))
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0-100, AI-assessed
    level: Mapped[str] = mapped_column(String(10))  # good / ok / bad (derived from score)
    summary_fr: Mapped[str | None] = mapped_column(String, nullable=True)
    summary_en: Mapped[str | None] = mapped_column(String, nullable=True)
    sources: Mapped[list | None] = mapped_column(JSON, default=list)
    # Structured extras for trend-lens criteria (community safety, safety, political stability):
    # {level: high|moderate|low, trend: improving|stable|worsening, window: str, metric: str}.
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Fingerprint of the prompt (template version + label + description) that produced this
    # row. When the prompt changes, the fingerprint changes, so the row is treated as stale and
    # re-evaluated — a prompt edit automatically dirties exactly the entries it affects.
    prompt_fp: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    freshness_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
