import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission
from app.exceptions import (
    BadRequestError,
    ForbiddenError,
    MissingServerPermissionError,
    ServerNotFoundError,
    UnprocessableEntityError,
)
from app.repositories.server import ServerRepository
from app.schemas.server import ServerUpdate
from app.services import storage
from app.services.channel_access import ChannelAccessService
from app.services.image import BANNER_SIZE, ICON_SIZE, normalize_image

ICONS_PREFIX = "server-icons"
# Dentro de server-icons/: es el único prefijo que el usuario IAM del servicio puede escribir y que el bucket
# publica (infra/terraform/locals.tf, media_writers). Un prefijo propio necesitaría un apply de Terraform.
BANNERS_PREFIX = f"{ICONS_PREFIX}/banners"


class ServerService:
    def __init__(self, repo: ServerRepository):
        self.repo = repo

    async def get_user_servers(self, db: AsyncSession, user_id: str):
        servers = await self.repo.get_user_servers(db, user_id)
        return await ChannelAccessService().attach_my_permissions(db, servers, user_id)

    async def get_mutual_servers(self, db: AsyncSession, viewer_id: str, other_user_id: str):
        return await self.repo.get_mutual_servers(db, viewer_id, other_user_id)

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

    async def update_server(self, db: AsyncSession, server_id: uuid.UUID, user_id: str, data: ServerUpdate):
        """Cambia nombre y/o descripción. Si no cambia nada, no guarda ni emite server.updated."""
        server = await self._get_manageable_server(db, server_id, user_id)
        changes = {field: value for field, value in data.changes().items() if getattr(server, field) != value}
        if not changes:
            return await self._with_my_permissions(db, server, user_id)

        try:
            updated = await self.repo.update_server(db, server, changes)
        except Exception:
            await db.rollback()
            raise
        return await self._with_my_permissions(db, updated, user_id)

    async def _replace_image(self, db: AsyncSession, server, file: UploadFile, field: str, prefix: str, size, save):
        """Sube la imagen nueva, la guarda y recién después borra la anterior. Si falla la base, borra la que
        subió (no la referencia nadie) y el servidor queda como estaba."""
        previous_url = getattr(server, field)

        image = normalize_image(await file.read(), size)
        new_url = await asyncio.to_thread(storage.upload_image, image, prefix)
        try:
            updated = await save(db, server, new_url)
        except Exception:
            await db.rollback()
            await asyncio.to_thread(storage.delete_image, new_url)
            raise

        if previous_url:
            await asyncio.to_thread(storage.delete_image, previous_url)
        return updated

    async def _remove_image(self, db: AsyncSession, server, field: str, save):
        """Quita la imagen y borra el archivo. Sin imagen no hace nada (ni emite el evento)."""
        previous_url = getattr(server, field)
        if previous_url is None:
            return server

        updated = await save(db, server, None)
        await asyncio.to_thread(storage.delete_image, previous_url)
        return updated

    async def update_icon(self, db: AsyncSession, server_id: uuid.UUID, user_id: str, icon: UploadFile):
        """Reemplaza el ícono (cuadrado de 256 px)."""
        server = await self._get_manageable_server(db, server_id, user_id)
        updated = await self._replace_image(db, server, icon, "icon_url", ICONS_PREFIX, ICON_SIZE, self.repo.set_icon)
        return await self._with_my_permissions(db, updated, user_id)

    async def remove_icon(self, db: AsyncSession, server_id: uuid.UUID, user_id: str):
        """Quita el ícono (el servidor vuelve a mostrar sus iniciales) y borra el archivo."""
        server = await self._get_manageable_server(db, server_id, user_id)
        updated = await self._remove_image(db, server, "icon_url", self.repo.set_icon)
        return await self._with_my_permissions(db, updated, user_id)

    async def update_banner(self, db: AsyncSession, server_id: uuid.UUID, user_id: str, banner: UploadFile):
        """Reemplaza el banner (16:9, 960x540)."""
        server = await self._get_manageable_server(db, server_id, user_id)
        updated = await self._replace_image(
            db, server, banner, "banner_url", BANNERS_PREFIX, BANNER_SIZE, self.repo.set_banner
        )
        return await self._with_my_permissions(db, updated, user_id)

    async def remove_banner(self, db: AsyncSession, server_id: uuid.UUID, user_id: str):
        """Quita el banner y borra el archivo."""
        server = await self._get_manageable_server(db, server_id, user_id)
        updated = await self._remove_image(db, server, "banner_url", self.repo.set_banner)
        return await self._with_my_permissions(db, updated, user_id)

    async def get_member_user_ids(self, db: AsyncSession, server_id: uuid.UUID) -> list[str]:
        """Miembros del servidor (endpoint interno, para que Chat avise un cambio por el inbox)."""
        if not await self.repo.get_server_by_id(db, server_id):
            raise ServerNotFoundError()
        return await self.repo.get_member_user_ids(db, server_id)

    async def delete_server(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> None:
        server = await self.repo.get_server_by_id(db, server_id)
        if not server:
            raise ServerNotFoundError()
        if server.owner_id != user_id:
            raise ForbiddenError("Only the server owner can delete this server.")

        image_urls = [url for url in (server.icon_url, server.banner_url) if url]
        await self.repo.delete_server(db, server)

        for url in image_urls:
            await asyncio.to_thread(storage.delete_image, url)

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

    async def get_member_growth(
        self,
        db: AsyncSession,
        server_id: uuid.UUID,
        user_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
        days: int | None = None,
    ) -> dict[str, Any]:
        """Consulta el gráfico de crecimiento de miembros (requiere MANAGE_SERVER, ADMINISTRATOR o dueño)."""
        await self._get_manageable_server(db, server_id, user_id)

        today = datetime.now(UTC).date()
        if start_date is not None and end_date is not None:
            if start_date > end_date:
                raise UnprocessableEntityError(detail="start_date cannot be after end_date")
            resolved_start = start_date
            resolved_end = end_date
        elif days is not None:
            resolved_end = today
            resolved_start = today - timedelta(days=max(0, days - 1))
        else:
            resolved_end = today
            resolved_start = today - timedelta(days=29)

        return await self.repo.get_member_growth(db, server_id, resolved_start, resolved_end)
