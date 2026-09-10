from pydantic import BaseModel, Field, ConfigDict
from typing import List
from uuid import UUID
from datetime import datetime
from app.schemas.channel import ChannelResponse

class ServerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, pattern=r"^[^\x00]+$")

class ServerResponse(BaseModel):
    id: UUID
    owner_id: UUID
    name: str
    icon_url: str | None
    created_at: datetime
    channels: List[ChannelResponse] = []

    model_config = ConfigDict(from_attributes=True)