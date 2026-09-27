from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InviteCreate(BaseModel):
    max_uses: int | None = Field(None, ge=1, description="Null for unlimited uses")
    expires_in_seconds: int | None = Field(None, ge=60, description="Null for no expiration")

class InviteResponse(BaseModel):
    code: str
    server_id: UUID
    inviter_id: str
    max_uses: int | None
    uses: int
    expires_at: datetime | None
    is_revoked: bool
    
    model_config = ConfigDict(from_attributes=True)

class InvitePreviewResponse(BaseModel):
    code: str
    server_id: UUID
    server_name: str
    server_description: str | None = None
    server_icon: str | None = None
    member_count: int
