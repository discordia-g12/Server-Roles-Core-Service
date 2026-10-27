from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.category import MAX_REORDER_ITEMS


class ChannelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., pattern="^(text|voice)$")
    category_id: UUID | None = None


class ChannelUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    topic: str | None = Field(None, max_length=1024)
    category_id: UUID | None = None

    model_config = ConfigDict(extra="forbid")


class ChannelOrderItem(BaseModel):
    id: UUID
    category_id: UUID | None = None

    model_config = ConfigDict(extra="forbid")


class ChannelReorder(BaseModel):

    channels: list[ChannelOrderItem] = Field(..., min_length=1, max_length=MAX_REORDER_ITEMS)

    model_config = ConfigDict(extra="forbid")


class ChannelResponse(BaseModel):
    id: UUID
    server_id: UUID | None = None
    name: str
    type: str
    position: int
    topic: str | None = None
    category_id: UUID | None = None
    # Permisos efectivos de quien pide en este canal (bitmask, con los overrides del canal); solo en las
    # respuestas que lo calculan (GET /servers)
    my_permissions: int | None = None

    model_config = ConfigDict(from_attributes=True)
