from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: str | None = Field(None, pattern="^#[0-9a-fA-F]{6}$")


class RoleUpdatePermissions(BaseModel):
    new_permissions_bitmask: int = Field(..., ge=0)


class RoleReorder(BaseModel):
    role_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=500)
    roles: list[UUID] | None = Field(default=None, min_length=1, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_ids(self) -> RoleReorder:
        if self.role_ids is None and self.roles is None:
            raise ValueError("Either role_ids or roles must be provided.")
        if self.role_ids is None:
            self.role_ids = self.roles
        return self

    def get_role_ids(self) -> list[UUID]:
        return self.role_ids or []


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


class RoleUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    color: str | None = Field(None, pattern="^#[0-9a-fA-F]{6}$")
