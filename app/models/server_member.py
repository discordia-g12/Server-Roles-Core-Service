import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class ServerMember(Base):
    __tablename__ = "server_members"
    __table_args__ = (UniqueConstraint("server_id", "user_id", name="uq_server_members_server_id_user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    server_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # user_id points to auth_db.users, a different service's database (Database-per-Service) — no FK.
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    nickname: Mapped[str | None] = mapped_column(String(100), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
