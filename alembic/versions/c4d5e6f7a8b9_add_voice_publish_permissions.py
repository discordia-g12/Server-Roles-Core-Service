"""add VIDEO and SCREEN_SHARE permissions

Revision ID: c4d5e6f7a8b9
Revises: b1a2c3d4e5f6
Create Date: 2026-10-26 23:00:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, Sequence[str], None] = 'b1a2c3d4e5f6'
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
    (21, "VIDEO", "Usar la cámara en canales de voz"),
    (22, "SCREEN_SHARE", "Compartir pantalla en canales de voz"),
]

CONNECT = 1 << 15
NEW_BITS = (1 << 21) | (1 << 22)


def upgrade() -> None:
    """Upgrade schema."""
    op.bulk_insert(
        permissions_table,
        [
            {"id": uuid.uuid4(), "bit_position": bit, "name": name, "description": description}
            for bit, name, description in PERMISSIONS
        ],
    )
    # Hasta ahora quien podía conectarse a voz podía publicar todo: los roles existentes con CONNECT
    # reciben los permisos nuevos para no perder la cámara
    op.execute(
        sa.text(
            "UPDATE roles SET permissions_bitmask = permissions_bitmask | :new_bits "
            "WHERE permissions_bitmask & :connect <> 0"
        ).bindparams(new_bits=NEW_BITS, connect=CONNECT)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        sa.text("UPDATE roles SET permissions_bitmask = permissions_bitmask & ~CAST(:new_bits AS BIGINT)").bindparams(
            new_bits=NEW_BITS
        )
    )
    op.execute(permissions_table.delete().where(permissions_table.c.bit_position.in_([21, 22])))
