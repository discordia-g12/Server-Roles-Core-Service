from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox_event import OutboxEvent


def add_outbox_event(db: AsyncSession, routing_key: str, payload: dict[str, Any]) -> None:
    """Adds the event to the actual session: it keeps the same commit as the change (Outbox, ADR-0004).
    The events only notifies what changed(ids); the client is resposible to ask again the info via API.
    """
    db.add(OutboxEvent(routing_key=routing_key, payload=payload))
