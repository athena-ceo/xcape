# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    locale: str = "fr"
    first_name: str | None = None
    last_name: str | None = None
    current_country: str | None = None  # if known; otherwise auto-detected


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    current_country: str | None = None
    citizenships: list[str] | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    first_name: str | None = None
    last_name: str | None = None
    current_country: str | None = None
    citizenships: list[str] = []
    is_admin: bool
    is_verified: bool
    locale: str
    created_at: datetime
