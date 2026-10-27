import asyncio
import uuid

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission
from app.exceptions import BadRequestError, MissingServerPermissionError, ServerNotFoundError
from app.repositories.server import ServerRepository
from app.services import storage
from app.services.channel_access import ChannelAccessService
from app.services.image import normalize_image

ICONS_PREFIX = "server-icons"


class ServerService:
    def __init__(self, repo: ServerRepository):
        self.repo = repo

    async def get_user_servers(self, db: AsyncSession, user_id: str):
        servers = await self.repo.get_user_servers(db, user_id)
        return await ChannelAccessService().attach_my_permissions(db, servers, user_id)

    async def _with_my_permissions(self, db: AsyncSession, server, user_id: str):
        """El servidor con my_permissions de quien pide (las respuestas de servidor siempre lo traen)."""
        await ChannelAccessService().attach_my_permissions(db, [server], user_id)
        return server

    async def create_server(
        self,
        db: AsyncSession,
        owner_id: str,
        server_name: str,
        icon: UploadFile | None,
    ):
        icon_url = None
        if icon is not None:
            # El ícono se sube antes de crear el servidor: si S3 falla, no queda un servidor a medias
            image = normalize_image(await icon.read())
            icon_url = await asyncio.to_thread(storage.upload_image, image, ICONS_PREFIX)

        try:
            server = await self.repo.create_server_with_defaults(db, owner_id, server_name, icon_url)
        except Exception:
            # Si falla la base, el ícono recién subido no lo referencia nadie
            await asyncio.to_thread(storage.delete_image, icon_url)
            raise
        return await self._with_my_permissions(db, server, owner_id)

    async def _get_manageable_server(self, db: AsyncSession, server_id: uuid.UUID, user_id: str):
        """El servidor, si el usuario es el dueño o tiene MANAGE_SERVER o ADMINISTRATOR en algún rol."""
        server = await self.repo.get_server_by_id(db, server_id)
        if not server:
            raise ServerNotFoundError()
        if server.owner_id == user_id:
            return server

        required = Permission.ADMINISTRATOR.value | Permission.MANAGE_SERVER.value
        bitmasks = await self.repo.get_member_permission_bitmasks(db, server_id, user_id)
        if not any(mask & required for mask in bitmasks):
            raise MissingServerPermissionError()
        return server

    async def update_icon(self, db: AsyncSession, server_id: uuid.UUID, user_id: str, icon: UploadFile):
        """Reemplaza el ícono: sube el nuevo, lo guarda y recién después borra el anterior."""
        server = await self._get_manageable_server(db, server_id, user_id)
        previous_url = server.icon_url

        image = normalize_image(await icon.read())
        icon_url = await asyncio.to_thread(storage.upload_image, image, ICONS_PREFIX)
        try:
            updated = await self.repo.set_icon(db, server, icon_url)
        except Exception:
            await db.rollback()
            await asyncio.to_thread(storage.delete_image, icon_url)
            raise

        await asyncio.to_thread(storage.delete_image, previous_url)
        return await self._with_my_permissions(db, updated, user_id)

    async def remove_icon(self, db: AsyncSession, server_id: uuid.UUID, user_id: str):
        """Quita el ícono (el servidor vuelve a mostrar sus iniciales) y borra el archivo."""
        server = await self._get_manageable_server(db, server_id, user_id)
        previous_url = server.icon_url
        if previous_url is None:
            return await self._with_my_permissions(db, server, user_id)

        updated = await self.repo.set_icon(db, server, None)
        await asyncio.to_thread(storage.delete_image, previous_url)
        return await self._with_my_permissions(db, updated, user_id)

    async def leave_server(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> None:
        server = await self.repo.get_server_by_id(db, server_id)
        if not server:
            raise ServerNotFoundError()
        
        if server.owner_id == user_id:
            raise BadRequestError("Owners cannot leave their own server directly. Transfer ownership or delete the server first.")  # noqa: E501
            
        member = await self.repo.get_server_member(db, server_id, user_id)
        if not member:
            raise BadRequestError("You are not a member of this server.")
            
        await self.repo.remove_member(db, member)

    async def get_server_members(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str, limit: int, offset: int
    ) -> dict:
        server = await self.repo.get_server_by_id(db, server_id)
        if not server:
            raise HTTPException(status_code=404, detail="Server not found.")
        if not await self.repo.is_member(db, server_id, user_id):
            raise HTTPException(status_code=403, detail="You are not a member of this server.")

        items, total = await self.repo.get_members_page(db, server_id, limit, offset)
        return {"items": items, "total": total, "limit": limit, "offset": offset}