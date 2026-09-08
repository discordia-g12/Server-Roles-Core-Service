"""seed permissions catalog

Revision ID: f2b24b03ae88
Revises: f151531ffcb7
Create Date: 2026-09-08 17:35:09.367470

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2b24b03ae88'
down_revision: Union[str, Sequence[str], None] = 'f151531ffcb7'
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
    (0, "VIEW_CHANNELS", "Ver canales del servidor"),
    (1, "MANAGE_CHANNELS", "Crear, editar y eliminar canales"),
    (2, "MANAGE_ROLES", "Crear, editar y eliminar roles"),
    (3, "MANAGE_SERVER", "Editar la configuración del servidor"),
    (4, "KICK_MEMBERS", "Expulsar miembros del servidor"),
    (5, "BAN_MEMBERS", "Banear miembros del servidor"),
    (6, "CREATE_INVITE", "Crear invitaciones al servidor"),
    (7, "CHANGE_NICKNAME", "Cambiar el propio apodo"),
    (8, "MANAGE_NICKNAMES", "Cambiar el apodo de otros miembros"),
    (9, "SEND_MESSAGES", "Enviar mensajes en canales de texto"),
    (10, "MANAGE_MESSAGES", "Editar o eliminar mensajes de otros"),
    (11, "EMBED_LINKS", "Insertar previews de links"),
    (12, "ATTACH_FILES", "Adjuntar archivos"),
    (13, "ADD_REACTIONS", "Agregar reacciones a mensajes"),
    (14, "MENTION_EVERYONE", "Mencionar @everyone / @here"),
    (15, "CONNECT", "Conectarse a canales de voz"),
    (16, "SPEAK", "Hablar en canales de voz"),
    (17, "MUTE_MEMBERS", "Silenciar miembros en voz"),
    (18, "DEAFEN_MEMBERS", "Ensordecer miembros en voz"),
    (19, "MOVE_MEMBERS", "Mover miembros entre canales de voz"),
    (20, "ADMINISTRATOR", "Bypassea todos los chequeos de permisos"),
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
    op.execute(permissions_table.delete())
