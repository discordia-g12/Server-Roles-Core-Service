import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any

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
from app.models.server_member_event import ServerMemberEvent
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
        db.add(ServerMemberEvent(server_id=server.id, user_id=owner_id, event_type="join"))
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

    async def update_server(self, db: AsyncSession, server: Server, changes: dict[str, Any]) -> Server:
        """Guarda los cambios de configuración (nombre, descripción, ícono, banner) y avisa con server.updated
        en el mismo commit. El evento lleva solo el id: cada cliente vuelve a pedir el servidor."""
        for field, value in changes.items():
            setattr(server, field, value)
        add_outbox_event(db, "server.updated", {"server_id": str(server.id)})
        await db.commit()
        await db.refresh(server, attribute_names=["channels", "categories"])
        return server

    async def set_icon(self, db: AsyncSession, server: Server, icon_url: str | None) -> Server:
        """Guarda el ícono nuevo (o None para quitarlo)."""
        return await self.update_server(db, server, {"icon_url": icon_url})

    async def set_banner(self, db: AsyncSession, server: Server, banner_url: str | None) -> Server:
        """Guarda el banner nuevo (o None para quitarlo)."""
        return await self.update_server(db, server, {"banner_url": banner_url})

    async def get_member_user_ids(self, db: AsyncSession, server_id: uuid.UUID) -> list[str]:
        """Ids de todos los miembros (para avisarles por el inbox de Chat). Sin paginar: es interno."""
        stmt = select(ServerMember.user_id).where(ServerMember.server_id == server_id).order_by(ServerMember.id)
        return list((await db.execute(stmt)).scalars().all())

    async def get_server_member(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> ServerMember | None:
        stmt = select(ServerMember).where(
            ServerMember.server_id == server_id,
            ServerMember.user_id == user_id
        )
        result = await db.execute(stmt)
        return result.scalars().first()
    
    async def remove_member(self, db: AsyncSession, member: ServerMember) -> None:
        db.add(ServerMemberEvent(server_id=member.server_id, user_id=member.user_id, event_type="leave"))
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

    async def get_member_growth(
        self, db: AsyncSession, server_id: uuid.UUID, start_date: date, end_date: date
    ) -> dict[str, Any]:
        start_datetime = datetime.combine(start_date, time.min)
        end_datetime = datetime.combine(end_date, time.max)

        stmt_baseline_joins = select(func.count()).select_from(ServerMemberEvent).where(
            ServerMemberEvent.server_id == server_id,
            ServerMemberEvent.event_type == "join",
            ServerMemberEvent.created_at < start_datetime,
        )
        baseline_joins = await db.scalar(stmt_baseline_joins) or 0

        stmt_baseline_leaves = select(func.count()).select_from(ServerMemberEvent).where(
            ServerMemberEvent.server_id == server_id,
            ServerMemberEvent.event_type.in_(["leave", "kick", "ban"]),
            ServerMemberEvent.created_at < start_datetime,
        )
        baseline_leaves = await db.scalar(stmt_baseline_leaves) or 0

        stmt_total_events = select(func.count()).select_from(ServerMemberEvent).where(
            ServerMemberEvent.server_id == server_id
        )
        total_events = await db.scalar(stmt_total_events) or 0

        if total_events == 0:
            stmt_old_members = select(func.count()).select_from(ServerMember).where(
                ServerMember.server_id == server_id,
                ServerMember.joined_at < start_datetime,
            )
            baseline = await db.scalar(stmt_old_members) or 0
        else:
            baseline = max(0, baseline_joins - baseline_leaves)

        if total_events > 0:
            stmt_events = (
                select(ServerMemberEvent)
                .where(
                    ServerMemberEvent.server_id == server_id,
                    ServerMemberEvent.created_at >= start_datetime,
                    ServerMemberEvent.created_at <= end_datetime,
                )
                .order_by(ServerMemberEvent.created_at.asc())
            )
            events = list((await db.execute(stmt_events)).scalars().all())
        else:
            stmt_members_in_period = select(ServerMember).where(
                ServerMember.server_id == server_id,
                ServerMember.joined_at >= start_datetime,
                ServerMember.joined_at <= end_datetime,
            )
            members_in_period = list((await db.execute(stmt_members_in_period)).scalars().all())
            events = [
                ServerMemberEvent(
                    server_id=m.server_id,
                    user_id=m.user_id,
                    event_type="join",
                    created_at=m.joined_at,
                )
                for m in members_in_period
            ]

        daily_joins: dict[date, int] = defaultdict(int)
        daily_leaves: dict[date, int] = defaultdict(int)
        for ev in events:
            ev_date = ev.created_at.date() if isinstance(ev.created_at, datetime) else ev.created_at
            if ev.event_type == "join":
                daily_joins[ev_date] += 1
            elif ev.event_type in ("leave", "kick", "ban"):
                daily_leaves[ev_date] += 1

        data = []
        curr = start_date
        running_count = baseline
        while curr <= end_date:
            joins_count = daily_joins[curr]
            leaves_count = daily_leaves[curr]
            running_count = max(0, running_count + joins_count - leaves_count)
            data.append({
                "date": curr.isoformat(),
                "member_count": running_count,
                "joined": joins_count,
                "left": leaves_count,
            })
            curr += timedelta(days=1)

        stmt_count = select(func.count()).select_from(ServerMember).where(ServerMember.server_id == server_id)
        current_count = await db.scalar(stmt_count) or 0

        return {
            "server_id": server_id,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": (end_date - start_date).days + 1,
            },
            "current_member_count": current_count,
            "data": data,
        }

