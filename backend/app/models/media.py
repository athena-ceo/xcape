# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MediaAsset(Base):
    """Drill-down media (maps/photos/links) discovered via web search, cached per Place."""

    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(10))  # map/photo/link
    url: Mapped[str] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)  # may hold long citations
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    place = relationship("Place", back_populates="media")
