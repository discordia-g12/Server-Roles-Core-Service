
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import DEFAULT_ROLE_PERMISSIONS
from app.models.channel import Channel
from app.models.role import Role
from app.models.role_assignment import RoleAssignment
from app.models.server import Server
from app.models.server_member import ServerMember
import uuid


class ServerRepository:
    async def get_user_servers(self, db: AsyncSession, user_id: str) -> list[Server]:
        stmt = (
            select(Server)
            .join(ServerMember, ServerMember.server_id == Server.id)
            .where(ServerMember.user_id == user_id)
            .order_by(Server.created_at.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def create_server_with_defaults(
        self, db: AsyncSession, owner_id: str, name: str, icon_url: str | None
    ) -> Server:
        server = Server(owner_id=owner_id, name=name, icon_url=icon_url)
        db.add(server)
        await db.flush() 

        text_channel = Channel(server_id=server.id, name="general", type="text", position=0)
        voice_channel = Channel(server_id=server.id, name="Voz General", type="voice", position=1)
        db.add_all([text_channel, voice_channel])

        default_role = Role(
            server_id=server.id,
            name="@everyone",
            position=0,
            permissions_bitmask=int(DEFAULT_ROLE_PERMISSIONS),
            is_default=True,
        )
        db.add(default_role)
        await db.flush()

        owner_member = ServerMember(server_id=server.id, user_id=owner_id)
        db.add(owner_member)
        await db.flush()

        db.add(RoleAssignment(server_member_id=owner_member.id, role_id=default_role.id))

        await db.commit()
        await db.refresh(server, attribute_names=["channels"])
        return server

    async def get_server_by_id(self, db: AsyncSession, server_id: uuid.UUID) -> Server | None:
        stmt = select(Server).where(Server.id == server_id)
        result = await db.execute(stmt)
        return result.scalars().first()
    
    async def get_server_member(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> ServerMember | None:
        stmt = select(ServerMember).where(
            ServerMember.server_id == server_id,
            ServerMember.user_id == user_id
        )
        result = await db.execute(stmt)
        return result.scalars().first()
    
    async def remove_member(self, db: AsyncSession, member: ServerMember) -> None:
        await db.delete(member)
        await db.commit()