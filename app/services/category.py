from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.category import CategoryRepository
from app.repositories.channel import ChannelRepository
from app.schemas.category import CategoryCreate


class CategoryService:
    def __init__(self, repo: CategoryRepository, channel_repo: ChannelRepository | None = None):
        self.repo = repo
        self.channel_repo = channel_repo or ChannelRepository()

    async def create_category(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str, category_data: CategoryCreate
    ):
        has_permission = await self.channel_repo.check_user_can_manage_channels(db, server_id, user_id)
        if not has_permission:
            raise HTTPException(
                status_code=403, 
                detail="You do not have permissions to manage categories in this server."
            )

        existing = await self.repo.get_category_by_name(db, server_id, category_data.name)
        if existing:
            raise HTTPException(
                status_code=400,
                detail="A category with that name already exists in this server."
            )

        return await self.repo.create_category(
            db, server_id, category_data.name, category_data.position
        )

    async def get_categories(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str
    ):
        return await self.repo.get_categories_by_server(db, server_id)

    async def delete_category(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str, category_id: uuid.UUID
    ):
        has_permission = await self.channel_repo.check_user_can_manage_channels(db, server_id, user_id)
        if not has_permission:
            raise HTTPException(
                status_code=403,
                detail="You do not have permissions to manage categories in this server."
            )

        category = await self.repo.get_category_by_id(db, server_id, category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Category not found.")

        await self.repo.delete_category(db, category)

