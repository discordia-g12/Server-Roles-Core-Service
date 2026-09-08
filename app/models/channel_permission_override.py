import uuid

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChannelPermissionOverride(Base):
    __tablename__ = "channel_permission_overrides"
    __table_args__ = (
        CheckConstraint(
            "(role_id IS NOT NULL) != (server_member_id IS NOT NULL)",
            name="role_xor_member",
        ),
        Index(
            "uq_channel_permission_overrides_channel_id_role_id",
            "channel_id",
            "role_id",
            unique=True,
            postgresql_where="role_id IS NOT NULL",
        ),
        Index(
            "uq_channel_permission_overrides_channel_id_server_member_id",
            "channel_id",
            "server_member_id",
            unique=True,
            postgresql_where="server_member_id IS NOT NULL",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=True
    )
    server_member_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("server_members.id", ondelete="CASCADE"), nullable=True
    )
    allow_bitmask: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    deny_bitmask: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
