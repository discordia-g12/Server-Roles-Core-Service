"""add VIEW_AUDIT_LOG permission

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-11-10 20:45:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, Sequence[str], None] = 'e6f7a8b9c0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

permissions_table = sa.table(
    "permissions",
    sa.column("id", sa.UUID()),
    sa.column("name", sa.String()),
    sa.column("bit_position", sa.SmallInteger()),
    sa.column("description", sa.String()),
)

PERMISSIONS = [
    (23, "VIEW_AUDIT_LOG", "Ver registro de auditoría del servidor"),
]


def upgrade() -> None:
    """Upgrade schema."""
    op.bulk_insert(
        permissions_table,
        [
            {"id": uuid.uuid4(), "bit_position": bit, "name": name, "description": description}
            for bit, name, description in PERMISSIONS
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        permissions_table.delete().where(permissions_table.c.bit_position == 23)
    )
