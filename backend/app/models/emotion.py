# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""The emotional layer (docs/xcape-plan-2026-10-feedback-and-emotion.md, Part B): the user's
hearted countries, and their per-country "postcard from your future" + pre-mortem."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Heart(Base):
    """A country the user hearted — a personal shelf that follows them across searches. It is
    a marker, not a score input: the numbers stay the same everywhere (board, explanation,
    assistant), and "heart vs numbers" is shown, not blended."""

    __tablename__ = "hearts"
    __table_args__ = (UniqueConstraint("user_id", "place_id", name="uq_heart_user_place"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    place = relationship("Place")


class Postcard(Base):
    """An AI-written "a day in your life there" vignette and a pre-mortem ("two years in, why
    you might be unhappy") for one user × country × language. Per-user (it is about THEIR
    household and hopes), cached, and regenerated when the inputs it was written from change
    (`fingerprint`)."""

    __tablename__ = "postcards"
    __table_args__ = (UniqueConstraint("user_id", "place_id", "lang", name="uq_postcard_user_place_lang"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"))
    lang: Mapped[str] = mapped_column(String(2))
    fingerprint: Mapped[str] = mapped_column(String(16))
    setting: Mapped[str | None] = mapped_column(String(120), nullable=True)  # the town it imagines
    postcard: Mapped[str] = mapped_column(Text)
    premortem: Mapped[list] = mapped_column(JSON, default=list)  # [{title, text}]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
