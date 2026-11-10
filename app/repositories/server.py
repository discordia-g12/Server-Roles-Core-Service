import uuid

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.permissions import DEFAULT_ROLE_PERMISSIONS
from app.models.channel import Channel
from app.models.role import Role
from app.models.role_assignment import RoleAssignment
from app.models.server import Server
from app.models.server_ban import ServerBan
from app.models.server_member import ServerMember
from app.repositories.outbox import add_outbox_event


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

    async def get_mutual_servers(self, db: AsyncSession, viewer_id: str, other_user_id: str) -> list:
        """Servidores donde están los dos y ninguno está baneado. Solo las columnas que usa el perfil público:
        sin cargar Server entero, que trae canales y categorías por selectin."""
        viewer = aliased(ServerMember)
        other = aliased(ServerMember)
        stmt = (
            select(Server.id, Server.name, Server.icon_url)
            .join(viewer, viewer.server_id == Server.id)
            .join(other, other.server_id == Server.id)
            .where(
                viewer.user_id == viewer_id,
                other.user_id == other_user_id,
                ~exists().where(
                    ServerBan.server_id == Server.id,
                    ServerBan.user_id.in_([viewer_id, other_user_id]),
                ),
            )
            .order_by(Server.created_at.asc(), Server.id.asc())
        )
        return list((await db.execute(stmt)).all())

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
        await db.refresh(server, attribute_names=["channels", "categories"])
        return server

    async def get_server_by_id(self, db: AsyncSession, server_id: uuid.UUID) -> Server | None:
        return await db.scalar(select(Server).where(Server.id == server_id))

    async def get_member_permission_bitmasks(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> list[int]:
        """Permisos de cada rol del usuario en el servidor (vacío si no es miembro)."""
        stmt = (
            select(Role.permissions_bitmask)
            .join(RoleAssignment, RoleAssignment.role_id == Role.id)
            .join(ServerMember, ServerMember.id == RoleAssignment.server_member_id)
            .where(ServerMember.server_id == server_id, ServerMember.user_id == user_id)
        )
        return list((await db.execute(stmt)).scalars().all())

    async def set_icon(self, db: AsyncSession, server: Server, icon_url: str | None) -> Server:
        """Guarda el ícono nuevo (o None para quitarlo) y avisa con server.updated en el mismo commit."""
        server.icon_url = icon_url
        add_outbox_event(db, "server.updated", {"server_id": str(server.id)})
        await db.commit()
        await db.refresh(server, attribute_names=["channels", "categories"])
        return server

    async def get_server_member(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> ServerMember | None:
        stmt = select(ServerMember).where(
            ServerMember.server_id == server_id,
            ServerMember.user_id == user_id
        )
        result = await db.execute(stmt)
        return result.scalars().first()
    
    async def remove_member(self, db: AsyncSession, member: ServerMember) -> None:
        add_outbox_event(db, "member.left", {"server_id": str(member.server_id), "user_id": member.user_id})
        await db.delete(member)
        await db.commit()

    async def is_member(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> bool:
        member_id = await db.scalar(
            select(ServerMember.id).where(ServerMember.server_id == server_id, ServerMember.user_id == user_id)
        )
        return member_id is not None

    async def get_members_page(
        self, db: AsyncSession, server_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[dict], int]:
        total = await db.scalar(
            select(func.count()).select_from(ServerMember).where(ServerMember.server_id == server_id)
        )

        members_query = (
            select(ServerMember)
            .where(ServerMember.server_id == server_id)
            .order_by(ServerMember.joined_at.asc(), ServerMember.id.asc())
            .limit(limit)
            .offset(offset)
        )
        members = list((await db.execute(members_query)).scalars().all())

        role_ids_by_member: dict[uuid.UUID, list[uuid.UUID]] = {member.id: [] for member in members}
        if members:
            assignments_query = select(RoleAssignment.server_member_id, RoleAssignment.role_id).where(
                RoleAssignment.server_member_id.in_(list(role_ids_by_member))
            )
            for member_id, role_id in (await db.execute(assignments_query)).all():
                role_ids_by_member[member_id].append(role_id)

        items = [
            {
                "id": member.id,
                "user_id": member.user_id,
                "nickname": member.nickname,
                "role_ids": role_ids_by_member[member.id],
            }
            for member in members
        ]
        return items, total or 0

    async def delete_server(self, db: AsyncSession, server: Server) -> list[uuid.UUID]:
        channel_ids_stmt = select(Channel.id).where(Channel.server_id == server.id)
        channel_ids = list((await db.execute(channel_ids_stmt)).scalars().all())

        add_outbox_event(
            db,
            "server.deleted",
            {
                "server_id": str(server.id),
                "channel_ids": [str(cid) for cid in channel_ids],
                "owner_id": server.owner_id,
            },
        )
        await db.delete(server)
        await db.commit()
        return channel_ids
