from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChannelRoleOverrideUpdate(BaseModel):
    """Excepción de permisos de un rol en un canal: lo que se permite y lo que se niega, además de lo del rol.

    Un permiso que no está en ninguno de los dos se hereda de los permisos generales del rol.
    """

    allow_bitmask: int = Field(0, ge=0)
    deny_bitmask: int = Field(0, ge=0)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_no_overlap(self) -> ChannelRoleOverrideUpdate:
        if self.allow_bitmask & self.deny_bitmask:
            raise ValueError("A permission cannot be allowed and denied at the same time.")
        return self


class ChannelRoleOverrideResponse(BaseModel):
    channel_id: UUID
    role_id: UUID
    allow_bitmask: int
    deny_bitmask: int

    model_config = ConfigDict(from_attributes=True)
