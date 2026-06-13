# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Search(Base):
    __tablename__ = "searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160), default="My search")
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/narrowing/decided
    criteria_set: Mapped[list | None] = mapped_column(JSON, default=list)  # ordered criterion keys
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user = relationship("User", back_populates="searches")
    candidates = relationship("Candidate", back_populates="search", cascade="all, delete-orphan")
    messages = relationship("ChatMessage", back_populates="search", cascade="all, delete-orphan")
