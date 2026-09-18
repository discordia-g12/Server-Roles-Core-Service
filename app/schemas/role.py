from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: str | None = Field(None, pattern="^#[0-9a-fA-F]{6}$")

class RoleUpdatePermissions(BaseModel):
    new_permissions_bitmask: int = Field(..., ge=0)

class RoleResponse(BaseModel):
    id: UUID
    name: str
    color: str | None
    position: int
    permissions_bitmask: int
    is_default: bool

    model_config = ConfigDict(from_attributes=True)

class RoleMemberResponse(BaseModel):
    id: UUID
    user_id: str
    nickname: str | None
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)

