# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SearchCreate(BaseModel):
    title: str = "My search"


class SearchUpdate(BaseModel):
    title: str | None = None
    status: str | None = None
    criteria_set: list[str] | None = None
    notes: str | None = None


class SearchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    status: str
    criteria_set: list[str] | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    place_id: int
    status: str
    match_score: float | None = None
    per_criterion: dict
    rank: int | None = None


class AddCandidateRequest(BaseModel):
    place_id: int | None = None
    place_name: str | None = None  # if set and not in DB, triggers AI research


class AddCriterionRequest(BaseModel):
    key: str
    label_fr: str | None = None
    label_en: str | None = None
