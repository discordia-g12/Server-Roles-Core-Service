from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.channel import ChannelResponse


class ServerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, pattern=r"^[^\x00]+$")

class ServerResponse(BaseModel):
    id: UUID
    owner_id: str
    name: str
    icon_url: str | None
    created_at: datetime
    channels: list[ChannelResponse] = []

    model_config = ConfigDict(from_attributes=True)


class ServerMemberResponse(BaseModel):
    id: UUID
    user_id: str
    nickname: str | None
    role_ids: list[UUID]


class ServerMemberPage(BaseModel):
    items: list[ServerMemberResponse]
    total: int
    limit: int
    offset: int
