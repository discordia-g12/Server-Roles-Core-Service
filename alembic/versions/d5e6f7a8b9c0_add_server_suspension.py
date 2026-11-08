"""add server suspension

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-11-08 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, Sequence[str], None] = 'c4d5e6f7a8b9'
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
