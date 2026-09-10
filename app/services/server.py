import uuid

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.server import ServerRepository

MAX_FILE_SIZE = 5 * 1024 * 1024
VALID_ICON_TYPES = {"image/jpeg", "image/png", "image/webp"}


class ServerService:
    def __init__(self, repo: ServerRepository):
        self.repo = repo

    async def create_server(
        self,
        db: AsyncSession,
        owner_id: uuid.UUID,
        server_name: str,
        icon: UploadFile | None,
    ):
        icon_url = None
        if icon is not None:
            if icon.content_type not in VALID_ICON_TYPES:
                raise HTTPException(400, "Formato no soportado. Usa JPEG, PNG o WebP.")

            file_bytes = await icon.read()
            if len(file_bytes) > MAX_FILE_SIZE:
                raise HTTPException(400, "Archivo demasiado grande. Límite 5MB.")

            # icon_url = await s3_provider.upload(file_bytes)  # TODO: definir storage

        return await self.repo.create_server_with_defaults(db, owner_id, server_name, icon_url)