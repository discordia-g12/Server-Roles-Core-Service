import uuid
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.channel import ChannelRepository
from app.schemas.channel import ChannelCreate

class ChannelService:
    def __init__(self, repo: ChannelRepository):
        self.repo = repo

    async def create_channel(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: uuid.UUID, channel_data: ChannelCreate
    ):
        has_permission = await self.repo.check_user_can_manage_channels(db, server_id, user_id)
        if not has_permission:
            raise HTTPException(
                status_code=403, 
                detail="No tienes permisos para crear canales en este servidor."
            )

        existing_channel = await self.repo.get_channel_by_name_and_category(
            db, server_id, channel_data.name, channel_data.category_id
        )
        if existing_channel:
            raise HTTPException(
                status_code=400, 
                detail="Ya existe un canal con ese nombre en esta categoría."
            )

        return await self.repo.create_channel(
            db, server_id, channel_data.name, channel_data.type, channel_data.category_id
        )