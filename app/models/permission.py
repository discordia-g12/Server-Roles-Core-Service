import uuid

from sqlalchemy import SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Permission(Base):
    """Static reference catalog of permission bits — not joined at request time.

    Permission checks are done via bitwise ops against Role.permissions_bitmask;
    this table only documents/validates which bit means what.
    """

    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    bit_position: Mapped[int] = mapped_column(SmallInteger, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
