from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class SuspendServerRequest(BaseModel):
    """Staff suspends a server (backoffice, "Suspender servidor completo")."""

    reason: str = Field(
        ...,
        min_length=1,
        max_length=512,
        pattern=r"^[^\x00]+$",
        description="Why: stored with the suspension and sent in the server.suspended event (audit)",
    )


class DeleteServerRequest(BaseModel):
    """Staff permanently deletes a server (backoffice, "Eliminar servidor desde el backoffice")."""

    reason: str | None = Field(
        default=None,
        min_length=1,
        max_length=512,
        pattern=r"^[^\x00]+$",
        description="Why: logged and sent in the server.deleted event (audit)",
    )

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Reason cannot be blank.")
        return trimmed


class DeletedServerResponse(BaseModel):
    """Summary returned after staff permanently deletes a server."""

    id: UUID
    name: str
    owner_id: str
    member_count: int
    deleted_by: str
    reason: str | None = None
    deleted_at: datetime


class AdminServerResponse(BaseModel):
    """A server as the backoffice shows it, with its suspension state."""

    id: UUID
    name: str
    owner_id: str
    icon_url: str | None
    member_count: int
    created_at: datetime
    is_suspended: bool
    suspended_at: datetime | None = None
    suspended_by: str | None = None
    suspension_reason: str | None = None


ServerStateFilter = Literal["all", "active", "suspended"]


class AdminServerPage(BaseModel):
    """A page of the platform's servers ("Ver listado de servidores de la plataforma")."""

    items: list[AdminServerResponse]
    total: int = Field(..., description="Servers matching the filters, across all pages")
    page: int
    page_size: int
