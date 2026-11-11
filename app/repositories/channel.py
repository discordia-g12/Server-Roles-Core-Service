import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission
from app.models.channel import Channel
from app.models.role import Role
from app.models.role_assignment import RoleAssignment
from app.models.server import Server
from app.models.server_member import ServerMember
from app.repositories.outbox import add_outbox_event


class ChannelRepository:
    async def get_channel_by_name_and_category(
        self, db: AsyncSession, server_id: uuid.UUID, name: str, category_id: uuid.UUID | None
    ) -> Channel | None:
        query = select(Channel).where(
            Channel.server_id == server_id,
            Channel.name == name,
            Channel.category_id == category_id
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_channels_by_server(self, db: AsyncSession, server_id: uuid.UUID) -> list[Channel]:
        query = select(Channel).where(Channel.server_id == server_id).order_by(Channel.position.asc())
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_next_position(self, db: AsyncSession, server_id: uuid.UUID) -> int:
        query = select(func.max(Channel.position)).where(Channel.server_id == server_id)
        result = await db.execute(query)
        max_pos = result.scalar()
        return (max_pos + 1) if max_pos is not None else 0

    async def create_channel(
        self,
        db: AsyncSession,
        server_id: uuid.UUID,
        name: str,
        type: str,
        category_id: uuid.UUID | None,
        created_by: str | None = None,
    ) -> Channel:
        position = await self.get_next_position(db, server_id)
        channel = Channel(
            server_id=server_id,
            name=name,
            type=type,
            category_id=category_id,
            position=position
        )
        db.add(channel)
        await db.flush()
        add_outbox_event(
            db,
            "channel.created",
            {
                "server_id": str(server_id),
                "channel_id": str(channel.id),
                "name": channel.name,
                "type": channel.type,
                "category_id": str(channel.category_id) if channel.category_id else None,
                "created_by": created_by,
            },
        )
        await db.commit()
        await db.refresh(channel)
        return channel

    async def check_user_can_manage_channels(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str
    ) -> bool:
        server = await db.scalar(select(Server).where(Server.id == server_id))
        if not server:
            return False
        if server.owner_id == user_id:
            return True
            
        query = (
            select(Role.permissions_bitmask)
            .join(RoleAssignment, RoleAssignment.role_id == Role.id)
            .join(ServerMember, ServerMember.id == RoleAssignment.server_member_id)
            .where(
                ServerMember.server_id == server_id,
                ServerMember.user_id == user_id
            )
        )
        result = await db.execute(query)
        bitmasks = result.scalars().all()
        
        required_bits = Permission.ADMINISTRATOR | Permission.MANAGE_CHANNELS
        
        for bitmask in bitmasks:
            if (bitmask & required_bits.value) != 0:
                return True
                
        return False

    async def get_channel_by_id(
        self, db: AsyncSession, server_id: uuid.UUID, channel_id: uuid.UUID
    ) -> Channel | None:
        query = select(Channel).where(
            Channel.server_id == server_id,
            Channel.id == channel_id
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def reorder_channels(
        self, db: AsyncSession, ordered: list[tuple[Channel, uuid.UUID | None]]
    ) -> list[Channel]:
        for position, (channel, category_id) in enumerate(ordered):
            channel.position = position
            channel.category_id = category_id
        if ordered:
            add_outbox_event(db, "channels.reordered", {"server_id": str(ordered[0][0].server_id)})
        await db.commit()
        return [channel for channel, _ in ordered]

    async def delete_channel(self, db: AsyncSession, channel: Channel, deleted_by: str | None = None) -> None:
        add_outbox_event(
            db,
            "channel.deleted",
            {
                "channel_id": str(channel.id),
                "server_id": str(channel.server_id),
                "name": channel.name,
                "type": channel.type,
                "deleted_by": deleted_by,
            },
        )
        await db.delete(channel)
        await db.commit()

    async def update_channel(
        self, db: AsyncSession, channel: Channel, update_data: dict, updated_by: str | None = None
    ) -> Channel:
        changes = {}
        for key, value in update_data.items():
            old_val = getattr(channel, key)
            if old_val != value:
                changes[key] = {
                    "old": str(old_val) if isinstance(old_val, uuid.UUID) else old_val,
                    "new": str(value) if isinstance(value, uuid.UUID) else value,
                }
            setattr(channel, key, value)
        add_outbox_event(
            db,
            "channel.updated",
            {
                "server_id": str(channel.server_id),
                "channel_id": str(channel.id),
                "name": channel.name,
                "changes": changes,
                "updated_by": updated_by,
            },
        )
        await db.commit()
        await db.refresh(channel)
        return channel