"""add server_member_events table

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-11-09 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, Sequence[str], None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'server_member_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('server_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.String(length=255), nullable=False),
        sa.Column('event_type', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['server_id'],
            ['servers.id'],
            name=op.f('fk_server_member_events_server_id_servers'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_server_member_events')),
    )
    op.create_index(
        'ix_server_member_events_server_id_created_at',
        'server_member_events',
        ['server_id', 'created_at'],
        unique=False,
    )
    op.create_index(
        op.f('ix_server_member_events_server_id'),
        'server_member_events',
        ['server_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_server_member_events_user_id'),
        'server_member_events',
        ['user_id'],
        unique=False,
    )

    # Backfill join events from existing server members
    op.execute(
        sa.text(
            """
            INSERT INTO server_member_events (id, server_id, user_id, event_type, created_at)
            SELECT gen_random_uuid(), server_id, user_id, 'join', joined_at
            FROM server_members
            """
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_server_member_events_user_id'), table_name='server_member_events')
    op.drop_index(op.f('ix_server_member_events_server_id'), table_name='server_member_events')
    op.drop_index('ix_server_member_events_server_id_created_at', table_name='server_member_events')
    op.drop_table('server_member_events')
