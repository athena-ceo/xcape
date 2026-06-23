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
    selected: bool = False
    override: str | None = None  # "in" pinned / "out" excluded by the user / None neutral
    match_score: float | None = None
    match_reasons: list[str] = []
    per_criterion: dict
    vs_current: dict[str, str] = {}  # criterion -> better/worse/same vs current country
    quality: dict[str, str] = {}     # criterion -> good/ok/bad (colour tier)
    reasons: dict[str, dict] = {}    # criterion -> {code, ...tokens} justification
    pending: list[str] = []          # criteria still being AI-evaluated (show a spinner)
    filter_violations: list[str] = []  # active hard filters this place fails (flag in UI)
    rank: int | None = None


class AddCandidateRequest(BaseModel):
    place_id: int | None = None
    place_name: str | None = None  # if set and not in DB, triggers AI research
    # When the board is already full, free a slot by de-selecting this place first (the explore
    # "replace the weakest" flow — the client chose which country to drop).
    evict_place_id: int | None = None


class AddCriterionRequest(BaseModel):
    key: str
    label_fr: str | None = None
    label_en: str | None = None


class AddCustomCriterionRequest(BaseModel):
    label: str
    description: str | None = None
    weight: float = 1.0


class UpdateCustomCriterionRequest(BaseModel):
    weight: float | None = None
    min: float | None = None  # 0-1 hard-filter threshold; null clears it


class SuggestCriteriaRequest(BaseModel):
    tags: list[str] = []
    text: str | None = None


class SetSelectedRequest(BaseModel):
    selected: bool
