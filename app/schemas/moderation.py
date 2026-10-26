import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BanCreate(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=255, pattern=r"^[^\x00]+$")
    reason: str | None = Field(None, max_length=500, pattern=r"^[^\x00]*$")


class BanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    server_id: uuid.UUID
    user_id: str
    banned_by: str | None = None
    reason: str | None = None
    created_at: datetime


class MuteCreate(BaseModel):
    user_id: str
    duration_seconds: int | None = None
    reason: str | None = None


class MuteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    server_id: uuid.UUID
    user_id: str
    muted_by: str | None = None
    expires_at: datetime | None = None
    reason: str | None = None
    created_at: datetime


class KickCreate(BaseModel):
    reason: str | None = None
