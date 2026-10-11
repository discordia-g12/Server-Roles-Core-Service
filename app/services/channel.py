from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.category import CategoryRepository
from app.repositories.channel import ChannelRepository
from app.schemas.channel import ChannelCreate, ChannelUpdate


class ChannelService:
    def __init__(self, repo: ChannelRepository, category_repo: CategoryRepository | None = None):
        self.repo = repo
        self.category_repo = category_repo or CategoryRepository()

    async def create_channel(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str, channel_data: ChannelCreate
    ):
        has_permission = await self.repo.check_user_can_manage_channels(db, server_id, user_id)
        if not has_permission:
            raise HTTPException(
                status_code=403, 
                detail="You do not have permissions to create channels in this server."
            )

        if channel_data.category_id is not None:
            category = await self.category_repo.get_category_by_id(db, server_id, channel_data.category_id)
            if not category:
                raise HTTPException(
                    status_code=404,
                    detail="Category not found."
                )

        existing_channel = await self.repo.get_channel_by_name_and_category(
            db, server_id, channel_data.name, channel_data.category_id
        )
        if existing_channel:
            raise HTTPException(
                status_code=400, 
                detail="A channel with that name already exists in this category."
            )

        return await self.repo.create_channel(
            db, server_id, channel_data.name, channel_data.type, channel_data.category_id
        )

    async def delete_channel(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str, channel_id: uuid.UUID
    ):
        has_permission = await self.repo.check_user_can_manage_channels(db, server_id, user_id)
        if not has_permission:
            raise HTTPException(
                status_code=403, 
                detail="You do not have permissions to delete channels in this server."
            )

        channel = await self.repo.get_channel_by_id(db, server_id, channel_id)
        if not channel:
            raise HTTPException(
                status_code=404,
                detail="Channel not found."
            )

        await self.repo.delete_channel(db, channel)

    async def update_channel(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str, channel_id: uuid.UUID, channel_data: ChannelUpdate
    ):
        has_permission = await self.repo.check_user_can_manage_channels(db, server_id, user_id)
        if not has_permission:
            raise HTTPException(
                status_code=403, 
                detail="You do not have permissions to edit channels in this server."
            )

        channel = await self.repo.get_channel_by_id(db, server_id, channel_id)
        if not channel:
            raise HTTPException(
                status_code=404,
                detail="Channel not found."
            )

        update_data = channel_data.model_dump(exclude_unset=True)
        if not update_data:
            return channel

        target_name = update_data.get("name", channel.name)
        target_category_id = update_data.get("category_id", channel.category_id)

        if "category_id" in update_data and update_data["category_id"] is not None:
            category = await self.category_repo.get_category_by_id(db, server_id, update_data["category_id"])
            if not category:
                raise HTTPException(
                    status_code=404,
                    detail="Category not found."
                )

        if target_name != channel.name or target_category_id != channel.category_id:
            existing_channel = await self.repo.get_channel_by_name_and_category(
                db, server_id, target_name, target_category_id
            )
            if existing_channel and existing_channel.id != channel.id:
                raise HTTPException(
                    status_code=400, 
                    detail="A channel with that name already exists in this category."
                )

        return await self.repo.update_channel(db, channel, update_data)