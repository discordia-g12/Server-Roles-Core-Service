import uuid
from datetime import datetime

from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class OutboxEvent(Base):
    """Transactional Outbox Pattern (ADR-0004): written in the same DB transaction
    as the business entity change, then relayed to RabbitMQ by an async worker.
    """

    __tablename__ = "outbox_events"
    __table_args__ = (Index("ix_outbox_events_status_created_at", "status", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    routing_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
