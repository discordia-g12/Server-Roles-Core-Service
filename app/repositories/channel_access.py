import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.models.channel import Channel
from app.models.channel_permission_override import ChannelPermissionOverride
from app.models.role import Role
from app.models.role_assignment import RoleAssignment
from app.models.server import Server
from app.models.server_ban import ServerBan
from app.models.server_member import ServerMember
from app.models.server_mute import ServerMute


class ChannelAccessRepository:
    """Consultas para calcular qué puede hacer un usuario en un canal (endpoints /internal)."""

    async def get_channel(self, db: AsyncSession, channel_id: uuid.UUID) -> Channel | None:
        return await db.scalar(select(Channel).where(Channel.id == channel_id))

    async def get_member(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> ServerMember | None:
        return await db.scalar(
            select(ServerMember).where(ServerMember.server_id == server_id, ServerMember.user_id == user_id)
        )

    async def is_banned(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> bool:
        ban_id = await db.scalar(
            select(ServerBan.id).where(ServerBan.server_id == server_id, ServerBan.user_id == user_id)
        )
        return ban_id is not None

    async def get_owner_id(self, db: AsyncSession, server_id: uuid.UUID) -> str | None:
        return await db.scalar(select(Server.owner_id).where(Server.id == server_id))

    async def get_member_roles(self, db: AsyncSession, member_id: uuid.UUID) -> list[tuple[uuid.UUID, int]]:
        """(role_id, permissions_bitmask) de cada rol del miembro."""
        result = await db.execute(
            select(Role.id, Role.permissions_bitmask)
            .join(RoleAssignment, RoleAssignment.role_id == Role.id)
            .where(RoleAssignment.server_member_id == member_id)
        )
        return [(role_id, bitmask) for role_id, bitmask in result.all()]

    async def get_channel_overrides(
        self, db: AsyncSession, channel_id: uuid.UUID, member_id: uuid.UUID, role_ids: list[uuid.UUID]
    ) -> list[ChannelPermissionOverride]:
        """Reglas del canal que aplican al miembro: las suyas y las de sus roles."""
        conditions = [ChannelPermissionOverride.server_member_id == member_id]
        if role_ids:
            conditions.append(ChannelPermissionOverride.role_id.in_(role_ids))
        result = await db.execute(
            select(ChannelPermissionOverride).where(
                ChannelPermissionOverride.channel_id == channel_id,
                or_(*conditions),
            )
        )
        return list(result.scalars().all())

    async def get_overrides_for_channels(
        self, db: AsyncSession, channel_ids: list[uuid.UUID], member_id: uuid.UUID, role_ids: list[uuid.UUID]
    ) -> list[ChannelPermissionOverride]:
        """Como get_channel_overrides, pero para varios canales en una sola consulta."""
        if not channel_ids:
            return []
        conditions = [ChannelPermissionOverride.server_member_id == member_id]
        if role_ids:
            conditions.append(ChannelPermissionOverride.role_id.in_(role_ids))
        result = await db.execute(
            select(ChannelPermissionOverride).where(
                ChannelPermissionOverride.channel_id.in_(channel_ids),
                or_(*conditions),
            )
        )
        return list(result.scalars().all())

    async def get_active_mute(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> ServerMute | None:
        """Mute vigente: sin vencimiento o que todavía no venció."""
        return await db.scalar(
            select(ServerMute).where(
                ServerMute.server_id == server_id,
                ServerMute.user_id == user_id,
                or_(ServerMute.expires_at.is_(None), ServerMute.expires_at > func.now()),
            )
        )
