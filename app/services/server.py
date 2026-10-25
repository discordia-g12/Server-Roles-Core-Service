import asyncio
import uuid

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import BadRequestError, ServerNotFoundError
from app.repositories.server import ServerRepository
from app.services import storage
from app.services.image import normalize_image

ICONS_PREFIX = "server-icons"


class ServerService:
    def __init__(self, repo: ServerRepository):
        self.repo = repo

    async def get_user_servers(self, db: AsyncSession, user_id: str):
        return await self.repo.get_user_servers(db, user_id)

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
            return await self.repo.create_server_with_defaults(db, owner_id, server_name, icon_url)
        except Exception:
            # Si falla la base, el ícono recién subido no lo referencia nadie
            await asyncio.to_thread(storage.delete_image, icon_url)
            raise

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