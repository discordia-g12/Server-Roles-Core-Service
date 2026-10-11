from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.category import Position


class ChannelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., pattern="^(text|voice)$")
    category_id: UUID | None = None


class ChannelUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    topic: str | None = Field(None, max_length=1024)
    category_id: UUID | None = None
    position: Position | None = None


class ChannelResponse(BaseModel):
    id: UUID
    server_id: UUID | None = None
    name: str
    type: str
    position: int
    topic: str | None = None
    category_id: UUID | None = None

    model_config = ConfigDict(from_attributes=True)