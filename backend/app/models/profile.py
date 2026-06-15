# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)

    household_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # single/couple/family
    # Whether a couple plans to have children — makes education a scored criterion.
    intends_children: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    origin_country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reasons_leaving: Mapped[list | None] = mapped_column(JSON, default=list)
    # Relocation archetype (registry persona key) — drives initial weights & onboarding questions.
    persona: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Free-text priorities (any number, beyond the preset chips) → AI criterion selection.
    priorities_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget_monthly: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tenure: Mapped[str | None] = mapped_column(String(10), nullable=True)  # rent/buy
    climate_pref: Mapped[str | None] = mapped_column(String(20), nullable=True)
    language_skills: Mapped[dict | None] = mapped_column(JSON, default=dict)
    must_haves: Mapped[list | None] = mapped_column(JSON, default=list)
    nice_to_haves: Mapped[list | None] = mapped_column(JSON, default=list)
    criteria_weights: Mapped[dict | None] = mapped_column(JSON, default=dict)
    # Hard constraints applied to the candidate pool, e.g. {"language_ease": true,
    # "climate": "warm", "safety": "high"} — see services.shortlist._passes_filters.
    filters: Mapped[dict | None] = mapped_column(JSON, default=dict)
    # Communities whose acceptance matters to the user (optional, private) — drives the
    # inclusion criterion, scored by the worst-accepted of these. See shortlist.MINORITY_GROUPS.
    minority_groups: Mapped[list | None] = mapped_column(JSON, default=list)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user = relationship("User", back_populates="profile")
