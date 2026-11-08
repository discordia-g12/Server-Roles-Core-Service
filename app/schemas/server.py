from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.category import CategoryResponse
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
    categories: list[CategoryResponse] = []
    # Permisos efectivos de quien pide (bitmask); solo en las respuestas que lo calculan
    my_permissions: int | None = None
    # Suspendido por el staff (ADR-002): sigue en la lista del miembro, con el cartel "suspended" y sin
    # canales ni categorías
    is_suspended: bool = False

    model_config = ConfigDict(from_attributes=True)


def member_server_view(server) -> ServerResponse:
    """Lo que ve un miembro: de un servidor suspendido, solo cuál es y que está suspendido."""
    view = ServerResponse.model_validate(server)
    if view.is_suspended:
        return view.model_copy(update={"channels": [], "categories": [], "my_permissions": 0})
    return view


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
