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
    ancestry_countries: list[str] | None = None
    locale: str | None = None


class AdminPasswordReset(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str | None = None
    last_name: str | None = None
    locale: str = "fr"
    is_admin: bool = False


class AdminUserActive(BaseModel):
    is_active: bool


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    first_name: str | None = None
    last_name: str | None = None
    current_country: str | None = None
    citizenships: list[str] | None = None  # NULL for accounts created before this field
    ancestry_countries: list[str] | None = None
    is_admin: bool
    is_verified: bool
    is_active: bool = True
    locale: str
    created_at: datetime
