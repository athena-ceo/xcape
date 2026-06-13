# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PlaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    parent_id: int | None = None
    name: str
    iso_code: str | None = None
    attributes: dict
    summary_fr: str | None = None
    summary_en: str | None = None
    source: str
    freshness_at: datetime


class MediaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    url: str
    caption: str | None = None
    source: str | None = None


class ChatRequest(BaseModel):
    message: str


class ChatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    created_at: datetime
