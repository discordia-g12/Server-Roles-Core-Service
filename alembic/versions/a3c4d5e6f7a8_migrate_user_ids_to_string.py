"""migrate user identifiers to string

Revision ID: a3c4d5e6f7a8
Revises: f2b24b03ae88
Create Date: 2026-09-15 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3c4d5e6f7a8"
down_revision: str | Sequence[str] | None = "f2b24b03ae88"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. servers.owner_id
    op.alter_column(
        "servers",
        "owner_id",
        existing_type=sa.UUID(),
        type_=sa.String(length=255),
        existing_nullable=False,
        postgresql_using="owner_id::varchar",
    )

    # 2. server_members.user_id
    op.alter_column(
        "server_members",
        "user_id",
        existing_type=sa.UUID(),
        type_=sa.String(length=255),
        existing_nullable=False,
        postgresql_using="user_id::varchar",
    )

    # 3. server_bans.user_id and banned_by
    op.alter_column(
        "server_bans",
        "user_id",
        existing_type=sa.UUID(),
        type_=sa.String(length=255),
        existing_nullable=False,
        postgresql_using="user_id::varchar",
    )
    op.alter_column(
        "server_bans",
        "banned_by",
        existing_type=sa.UUID(),
        type_=sa.String(length=255),
        existing_nullable=True,
        postgresql_using="banned_by::varchar",
    )

    # 4. server_mutes.user_id and muted_by
    op.alter_column(
        "server_mutes",
        "user_id",
        existing_type=sa.UUID(),
        type_=sa.String(length=255),
        existing_nullable=False,
        postgresql_using="user_id::varchar",
    )
    op.alter_column(
        "server_mutes",
        "muted_by",
        existing_type=sa.UUID(),
        type_=sa.String(length=255),
        existing_nullable=True,
        postgresql_using="muted_by::varchar",
    )


def downgrade() -> None:
    op.alter_column(
        "server_mutes",
        "muted_by",
        existing_type=sa.String(length=255),
        type_=sa.UUID(),
        existing_nullable=True,
        postgresql_using="muted_by::uuid",
    )
    op.alter_column(
        "server_mutes",
        "user_id",
        existing_type=sa.String(length=255),
        type_=sa.UUID(),
        existing_nullable=False,
        postgresql_using="user_id::uuid",
    )
    op.alter_column(
        "server_bans",
        "banned_by",
        existing_type=sa.String(length=255),
        type_=sa.UUID(),
        existing_nullable=True,
        postgresql_using="banned_by::uuid",
    )
    op.alter_column(
        "server_bans",
        "user_id",
        existing_type=sa.String(length=255),
        type_=sa.UUID(),
        existing_nullable=False,
        postgresql_using="user_id::uuid",
    )
    op.alter_column(
        "server_members",
        "user_id",
        existing_type=sa.String(length=255),
        type_=sa.UUID(),
        existing_nullable=False,
        postgresql_using="user_id::uuid",
    )
    op.alter_column(
        "servers",
        "owner_id",
        existing_type=sa.String(length=255),
        type_=sa.UUID(),
        existing_nullable=False,
        postgresql_using="owner_id::uuid",
    )

