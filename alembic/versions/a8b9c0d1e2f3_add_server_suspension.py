"""add server suspension

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-11-08 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a8b9c0d1e2f3'
down_revision: Union[str, Sequence[str], None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('servers', sa.Column('suspended_at', sa.DateTime(), nullable=True))
    op.add_column('servers', sa.Column('suspended_by', sa.String(length=255), nullable=True))
    op.add_column('servers', sa.Column('suspension_reason', sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column('servers', 'suspension_reason')
    op.drop_column('servers', 'suspended_by')
    op.drop_column('servers', 'suspended_at')
