from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ServerTransferCreate(BaseModel):
    target_user_id: str = Field(..., min_length=1, max_length=255)


class ServerTransferResponse(BaseModel):
    id: uuid.UUID
    server_id: uuid.UUID
    sender_id: str
    target_user_id: str
    status: str
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)