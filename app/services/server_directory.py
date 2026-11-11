import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.server import Server
from app.models.server_member import ServerMember
from app.schemas.admin import AdminServerPage, AdminServerResponse, ServerStateFilter


def _escape_like(value: str) -> str:
    """Que % y _ del texto buscado se tomen literales (el ESCAPE es la barra invertida)."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


class ServerDirectoryService:
    """Listado de servidores de la plataforma para el backoffice (solo staff).

    Búsqueda por nombre (parcial, sin distinguir mayúsculas) o por id exacto, filtro por estado de suspensión y
    paginado. Devuelve el id de cada servidor: con él se suspende (el nombre no es único, ADR-002).
    """

    async def list_servers(
        self,
        db: AsyncSession,
        *,
        query: str | None,
        state: ServerStateFilter,
        page: int,
        page_size: int,
    ) -> AdminServerPage:
        conditions = []
        text = (query or "").strip()
        if text:
            server_id = _as_uuid(text)
            if server_id is not None:
                conditions.append(Server.id == server_id)
            else:
                conditions.append(Server.name.ilike(f"%{_escape_like(text)}%", escape="\\"))
        if state == "active":
            conditions.append(Server.suspended_at.is_(None))
        elif state == "suspended":
            conditions.append(Server.suspended_at.is_not(None))

        total = await db.scalar(select(func.count()).select_from(Server).where(*conditions))

        # Miembros en la misma consulta (un servidor sin miembros cuenta 0)
        members = (
            select(ServerMember.server_id, func.count().label("member_count"))
            .group_by(ServerMember.server_id)
            .subquery()
        )
        rows = await db.execute(
            select(Server, func.coalesce(members.c.member_count, 0))
            .outerjoin(members, members.c.server_id == Server.id)
            .where(*conditions)
            .order_by(Server.created_at.desc(), Server.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        items = [
            AdminServerResponse(
                id=server.id,
                name=server.name,
                owner_id=server.owner_id,
                icon_url=server.icon_url,
                member_count=int(member_count),
                created_at=server.created_at,
                is_suspended=server.is_suspended,
                suspended_at=server.suspended_at,
                suspended_by=server.suspended_by,
                suspension_reason=server.suspension_reason,
            )
            for server, member_count in rows.all()
        ]
        return AdminServerPage(items=items, total=int(total or 0), page=page, page_size=page_size)
