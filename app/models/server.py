import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.channel import Channel


class Server(Base):
    __tablename__ = "servers"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(onupdate=func.now(), nullable=True)
    # Suspensión por el staff de la plataforma (docs/ADR-002-Suspension-de-Servidores.md): cuándo, quién y por
    # qué. Vacíos si no está suspendido. El contenido no se toca: al levantarla todo vuelve como estaba
    suspended_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)
    suspended_by: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    suspension_reason: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)

    @property
    def is_suspended(self) -> bool:
        return self.suspended_at is not None

    channels: Mapped[list["Channel"]] = relationship(
        "Channel", lazy="selectin", order_by="Channel.position", viewonly=False
    )
    categories: Mapped[list["Category"]] = relationship(
        "Category", lazy="selectin", order_by="Category.position", viewonly=False
    )