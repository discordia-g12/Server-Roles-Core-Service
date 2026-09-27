import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission
from app.models.channel import Channel
from app.models.outbox_event import OutboxEvent
from app.models.role import Role
from app.models.role_assignment import RoleAssignment
from app.models.server import Server
from app.models.server_member import ServerMember


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

    async def get_next_position(self, db: AsyncSession, server_id: uuid.UUID) -> int:
        query = select(func.max(Channel.position)).where(Channel.server_id == server_id)
        result = await db.execute(query)
        max_pos = result.scalar()
        return (max_pos + 1) if max_pos is not None else 0

    async def create_channel(
        self, db: AsyncSession, server_id: uuid.UUID, name: str, type: str, category_id: uuid.UUID | None
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

    async def delete_channel(self, db: AsyncSession, channel: Channel) -> None:
        event = OutboxEvent(
            routing_key="channel.deleted",
            payload={"channel_id": str(channel.id), "server_id": str(channel.server_id)}
        )
        db.add(event)
        await db.delete(channel)
        await db.commit()

    async def update_channel(
        self, db: AsyncSession, channel: Channel, update_data: dict
    ) -> Channel:
        for key, value in update_data.items():
            setattr(channel, key, value)
        await db.commit()
        await db.refresh(channel)
        return channel