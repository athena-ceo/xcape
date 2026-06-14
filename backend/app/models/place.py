# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Place(Base):
    """A country or region in the built-in, AI-refreshable database."""

    __tablename__ = "places"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10), index=True)  # country/region
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("places.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120), index=True)
    iso_code: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)

    # Structured criteria values (cost_of_living, climate, language, healthcare,
    # safety, political_stability, tax, visa, ...). Free-form to allow new criteria.
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    summary_fr: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_en: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Drill-down caches: basic facts (population, capital, flag, coords…) from a facts
    # API, and AI-written per-criterion detail with sources, keyed by language.
    facts: Mapped[dict] = mapped_column(JSON, default=dict)
    criteria_detail: Mapped[dict] = mapped_column(JSON, default=dict)

    # Deactivated places are kept but excluded from the shortlist pool / picker (admins
    # deactivate rather than delete).
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=func.true())
    source: Mapped[str] = mapped_column(String(10), default="seed")  # seed/ai
    freshness_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    children = relationship("Place", cascade="all, delete-orphan")
    media = relationship("MediaAsset", back_populates="place", cascade="all, delete-orphan")
