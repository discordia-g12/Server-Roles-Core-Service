"""add server_ownership_transfers table

Revision ID: b1a2c3d4e5f6
Revises: 9ce55c35affc
Create Date: 2026-10-13 18:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1a2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '9ce55c35affc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'server_ownership_transfers',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('server_id', sa.UUID(), nullable=False),
        sa.Column('sender_id', sa.String(length=255), nullable=False),
        sa.Column('target_user_id', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='PENDING'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['server_id'], ['servers.id'], name=op.f('fk_server_ownership_transfers_server_id_servers'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_server_ownership_transfers'))
    )
    op.create_index(op.f('ix_server_ownership_transfers_server_id'), 'server_ownership_transfers', ['server_id'], unique=False)
    op.create_index(op.f('ix_server_ownership_transfers_target_user_id'), 'server_ownership_transfers', ['target_user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_server_ownership_transfers_target_user_id'), table_name='server_ownership_transfers')
    op.drop_index(op.f('ix_server_ownership_transfers_server_id'), table_name='server_ownership_transfers')
    op.drop_table('server_ownership_transfers')