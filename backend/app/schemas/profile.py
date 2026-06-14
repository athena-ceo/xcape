# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from pydantic import BaseModel, ConfigDict


class ProfileUpdate(BaseModel):
    household_type: str | None = None
    intends_children: bool | None = None
    origin_country: str | None = None
    reasons_leaving: list[str] | None = None
    priorities_text: str | None = None
    budget_monthly: int | None = None
    tenure: str | None = None
    climate_pref: str | None = None
    language_skills: dict | None = None
    must_haves: list[str] | None = None
    nice_to_haves: list[str] | None = None
    criteria_weights: dict | None = None
    filters: dict | None = None
    minority_groups: list[str] | None = None


class ProfileOut(ProfileUpdate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
