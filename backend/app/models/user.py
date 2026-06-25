# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Where the user currently lives (the place they're moving FROM). Used as the
    # systematic comparison baseline. Defaulted at registration (geo-IP -> locale ->
    # France) and editable later.
    current_country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # ISO alpha-2 codes of the citizenships held across the moving household (the user
    # and any spouse/children). Drives visa / ease-of-movement scoring, which depends on
    # citizenship, not residence (e.g. a US citizen residing in France has no EU mobility).
    citizenships: Mapped[list | None] = mapped_column(JSON, default=list)
    # ISO alpha-2 codes where the household may claim residence/citizenship by ANCESTRY or
    # descent (user-declared — can't be inferred). A strong, easy visa pathway to those places.
    ancestry_countries: Mapped[list | None] = mapped_column(JSON, default=list)
    # Ethno-religious heritage that may grant a right-of-return INDEPENDENT of a country of
    # ancestry (e.g. "jewish" → Israel's Law of Return, Germany Art.116, Sephardic routes).
    # Keys from visa_pathways.HERITAGE_COUNTRIES; surfaces those countries' heritage pathways.
    heritages: Mapped[list | None] = mapped_column(JSON, default=list)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Soft-disable: a deactivated account is blocked from logging in but keeps all its data and
    # can be re-enabled by an admin (distinct from a permanent delete).
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default=true())
    locale: Mapped[str] = mapped_column(String(5), default="fr", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    profile = relationship("Profile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    searches = relationship("Search", back_populates="user", cascade="all, delete-orphan")
