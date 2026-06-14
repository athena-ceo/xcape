# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from datetime import datetime

from sqlalchemy import (
    JSON, DateTime, ForeignKey, String, UniqueConstraint, func,
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
    level: Mapped[str] = mapped_column(String(10))  # good / ok / bad
    summary_fr: Mapped[str | None] = mapped_column(String, nullable=True)
    summary_en: Mapped[str | None] = mapped_column(String, nullable=True)
    sources: Mapped[list | None] = mapped_column(JSON, default=list)
    freshness_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
