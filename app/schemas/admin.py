from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SuspendServerRequest(BaseModel):
    """Staff suspends a server (backoffice, "Suspender servidor completo")."""

    reason: str = Field(
        ...,
        min_length=1,
        max_length=512,
        pattern=r"^[^\x00]+$",
        description="Why: stored with the suspension and sent in the server.suspended event (audit)",
    )


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
