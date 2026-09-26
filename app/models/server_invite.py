import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class ServerInvite(Base):
    __tablename__ = "server_invites"

    code: Mapped[str] = mapped_column(String(16), primary_key=True) 
    server_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    inviter_id: Mapped[str] = mapped_column(String(255), nullable=False)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True) 
    uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True) 
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False) 
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)