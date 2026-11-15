import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConflictError, ServerNotFoundError
from app.models.server import Server
from app.models.server_member import ServerMember
from app.repositories.outbox import add_outbox_event
from app.schemas.admin import AdminServerResponse

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    # Las fechas de esta base se guardan en UTC sin zona (como created_at)
    return datetime.now(UTC).replace(tzinfo=None)


class ServerSuspensionService:
    """Suspender y levantar la suspensión de un servidor (docs/ADR-002-Suspension-de-Servidores.md).

    El servidor se identifica solo por su id: el nombre no es único. No se borra ni se cambia nada del contenido;
    el bloqueo lo hacen reject_suspended_server (rutas del servidor) y ChannelAccessService (Chat y Voz). El cambio
    y su evento van en la misma transacción (Outbox): Chat y Voz cierran las conexiones con server.suspended.
    """

    async def _get(self, db: AsyncSession, server_id: uuid.UUID) -> Server:
        server = await db.scalar(select(Server).where(Server.id == server_id))
        if server is None:
            raise ServerNotFoundError()
        return server

    async def _member_count(self, db: AsyncSession, server_id: uuid.UUID) -> int:
        count = await db.scalar(
            select(func.count()).select_from(ServerMember).where(ServerMember.server_id == server_id)
        )
        return int(count or 0)

    async def _to_response(self, db: AsyncSession, server: Server) -> AdminServerResponse:
        return AdminServerResponse(
            id=server.id,
            name=server.name,
            owner_id=server.owner_id,
            icon_url=server.icon_url,
            member_count=await self._member_count(db, server.id),
            created_at=server.created_at,
            is_suspended=server.is_suspended,
            suspended_at=server.suspended_at,
            suspended_by=server.suspended_by,
            suspension_reason=server.suspension_reason,
        )

    async def suspend(
        self, db: AsyncSession, server_id: uuid.UUID, reason: str, staff_user_id: str
    ) -> AdminServerResponse:
        server = await self._get(db, server_id)
        if server.is_suspended:
            raise ConflictError("The server is already suspended.")

        now = _utcnow()
        server.suspended_at = now
        server.suspended_by = staff_user_id
        server.suspension_reason = reason.strip()
        add_outbox_event(
            db,
            "server.suspended",
            {
                "server_id": str(server.id),
                # Voz saca a todos de estas llamadas; Chat cierra las sesiones por server_id
                "voice_channel_ids": [str(ch.id) for ch in server.channels if ch.type == "voice"],
                "reason": server.suspension_reason,
                "suspended_by": staff_user_id,
                "suspended_at": now.isoformat() + "Z",
            },
        )
        response = await self._to_response(db, server)
        await db.commit()
        logger.info("server_suspended server_id=%s suspended_by=%s", server.id, staff_user_id)
        return response

    async def lift(self, db: AsyncSession, server_id: uuid.UUID, staff_user_id: str) -> AdminServerResponse:
        server = await self._get(db, server_id)
        if not server.is_suspended:
            raise ConflictError("The server is not suspended.")

        server.suspended_at = None
        server.suspended_by = None
        server.suspension_reason = None
        add_outbox_event(
            db,
            "server.unsuspended",
            {
                "server_id": str(server.id),
                "lifted_by": staff_user_id,
                "lifted_at": _utcnow().isoformat() + "Z",
            },
        )
        response = await self._to_response(db, server)
        await db.commit()
        logger.info("server_suspension_lifted server_id=%s lifted_by=%s", server.id, staff_user_id)
        return response

    async def list_suspended(self, db: AsyncSession) -> list[AdminServerResponse]:
        result = await db.execute(
            select(Server).where(Server.suspended_at.is_not(None)).order_by(Server.suspended_at.desc())
        )
        return [await self._to_response(db, server) for server in result.scalars().all()]
