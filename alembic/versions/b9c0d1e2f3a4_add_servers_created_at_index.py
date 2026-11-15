"""add index on servers.created_at

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-11-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'b9c0d1e2f3a4'
down_revision: Union[str, Sequence[str], None] = 'a8b9c0d1e2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Métricas del backoffice: GET /internal/metrics/servers cuenta por rango de created_at
    op.create_index(op.f('ix_servers_created_at'), 'servers', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_servers_created_at'), table_name='servers')
