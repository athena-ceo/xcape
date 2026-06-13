# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Candidate(Base):
    """A Place pinned into a Search, with cached per-criterion values + score."""

    __tablename__ = "candidates"
    __table_args__ = (UniqueConstraint("search_id", "place_id", name="uq_candidate_search_place"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[int] = mapped_column(ForeignKey("searches.id", ondelete="CASCADE"), index=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(10), default="active")  # active/removed
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    per_criterion: Mapped[dict] = mapped_column(JSON, default=dict)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pinned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    search = relationship("Search", back_populates="candidates")
    place = relationship("Place")
