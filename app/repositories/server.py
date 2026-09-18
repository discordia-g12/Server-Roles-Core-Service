
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import DEFAULT_ROLE_PERMISSIONS
from app.models.channel import Channel
from app.models.role import Role
from app.models.role_assignment import RoleAssignment
from app.models.server import Server
from app.models.server_member import ServerMember


class ServerRepository:
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