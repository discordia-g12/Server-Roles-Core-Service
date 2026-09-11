from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID

class RoleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: str | None = Field(None, pattern="^#[0-9a-fA-F]{6}$")

class RoleResponse(BaseModel):
    id: UUID
    name: str
    color: str | None
    position: int
    permissions_bitmask: int
    is_default: bool

    model_config = ConfigDict(from_attributes=True)

