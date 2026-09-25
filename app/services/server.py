
from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
from app.exceptions import ServerNotFoundError, BadRequestError

from app.repositories.server import ServerRepository


MAX_FILE_SIZE = 5 * 1024 * 1024
VALID_ICON_TYPES = {"image/jpeg", "image/png", "image/webp"}


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
            if icon.content_type not in VALID_ICON_TYPES:
                raise HTTPException(400, "Unsupported format. Use JPEG, PNG or WebP.")

            file_bytes = await icon.read()
            if len(file_bytes) > MAX_FILE_SIZE:
                raise HTTPException(400, "File too large. Limit 5MB.")

            # icon_url = await s3_provider.upload(file_bytes)  # TODO: definir storage

        return await self.repo.create_server_with_defaults(db, owner_id, server_name, icon_url)

    async def leave_server(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> None:
        server = await self.repo.get_server_by_id(db, server_id)
        if not server:
            raise ServerNotFoundError()
        
        if server.owner_id == user_id:
            raise BadRequestError("Owners cannot leave their own server directly. Transfer ownership or delete the server first.")
            
        member = await self.repo.get_server_member(db, server_id, user_id)
        if not member:
            raise BadRequestError("You are not a member of this server.")
            
        await self.repo.remove_member(db, member)