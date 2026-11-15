import uuid

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.exceptions import ServerSuspendedError
from app.models.server import Server

# Lo único que se puede hacer en un servidor suspendido: irse (no es usarlo, y no hace falta retener a nadie)
ALLOWED_WHILE_SUSPENDED = ("/leave",)


async def reject_suspended_server(request: Request, db: AsyncSession = Depends(get_db)) -> None:
    """Router-wide guard (docs/ADR-002-Suspension-de-Servidores.md): any route with {server_id} answers
    403 server-suspended while the server is suspended. One place for the ~40 member routes (channels, roles,
    members, invites, moderation, transfers), so a new route cannot forget it.

    Staff endpoints live in another router (app/api/admin.py) and are not affected.
    """
    raw_id = request.path_params.get("server_id")
    if raw_id is None or request.url.path.endswith(ALLOWED_WHILE_SUSPENDED):
        return
    try:
        server_id = uuid.UUID(str(raw_id))
    except ValueError:
        return  # la ruta responde 422 sola
    suspended_at = await db.scalar(select(Server.suspended_at).where(Server.id == server_id))
    if suspended_at is not None:
        raise ServerSuspendedError()
