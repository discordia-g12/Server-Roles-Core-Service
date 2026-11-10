from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.category import CategoryResponse
from app.schemas.channel import ChannelResponse

DESCRIPTION_MAX_LENGTH = 1000

# Mismas reglas que al crear el servidor, pero con trim: "   " no es un nombre
ServerName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100, pattern=r"^[^\x00]+$")
]
ServerDescription = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_MAX_LENGTH, pattern=r"^[^\x00]*$")
]


class ServerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, pattern=r"^[^\x00]+$")


class ServerUpdate(BaseModel):
    """PATCH /servers/{id}: solo los campos que se mandan. La descripción vacía o null la borra."""

    name: ServerName | None = None
    description: ServerDescription | None = None

    # Un campo desconocido (owner_id, icon_url...) es un error, no algo que se ignora en silencio
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def check_fields(self) -> ServerUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field is required: name or description.")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null.")
        return self

    def changes(self) -> dict[str, str | None]:
        """Campos a guardar, con la descripción vacía normalizada a None."""
        values = self.model_dump(include=self.model_fields_set)
        if "description" in values and not values["description"]:
            values["description"] = None
        return values


class ServerResponse(BaseModel):
    id: UUID
    owner_id: str
    name: str
    description: str | None = None
    icon_url: str | None
    banner_url: str | None = None
    created_at: datetime
    channels: list[ChannelResponse] = []
    categories: list[CategoryResponse] = []
    # Permisos efectivos de quien pide (bitmask); solo en las respuestas que lo calculan
    my_permissions: int | None = None

    model_config = ConfigDict(from_attributes=True)


class MutualServerResponse(BaseModel):
    id: UUID
    name: str
    icon_url: str | None

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


class MemberGrowthPoint(BaseModel):
    date: str
    member_count: int
    joined: int
    left: int


class MemberGrowthPeriod(BaseModel):
    start_date: str
    end_date: str
    days: int


class MemberGrowthResponse(BaseModel):
    server_id: UUID
    period: MemberGrowthPeriod
    current_member_count: int
    data: list[MemberGrowthPoint]

