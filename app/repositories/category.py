from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category


class CategoryRepository:
    async def get_categories_by_server(self, db: AsyncSession, server_id: uuid.UUID) -> list[Category]:
        query = select(Category).where(
            Category.server_id == server_id
        ).order_by(Category.position.asc())
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_category_by_id(
        self, db: AsyncSession, server_id: uuid.UUID, category_id: uuid.UUID
    ) -> Category | None:
        query = select(Category).where(
            Category.server_id == server_id,
            Category.id == category_id
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_category_by_name(
        self, db: AsyncSession, server_id: uuid.UUID, name: str
    ) -> Category | None:
        query = select(Category).where(
            Category.server_id == server_id,
            Category.name == name
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_next_position(self, db: AsyncSession, server_id: uuid.UUID) -> int:
        query = select(func.max(Category.position)).where(Category.server_id == server_id)
        result = await db.execute(query)
        max_pos = result.scalar()
        return (max_pos + 1) if max_pos is not None else 0

    async def create_category(
        self, db: AsyncSession, server_id: uuid.UUID, name: str, position: int | None = None
    ) -> Category:
        if position is None:
            position = await self.get_next_position(db, server_id)
        category = Category(server_id=server_id, name=name, position=position)
        db.add(category)
        await db.commit()
        await db.refresh(category)
        return category

    async def update_category(self, db: AsyncSession, category: Category, update_data: dict) -> Category:
        for key, value in update_data.items():
            setattr(category, key, value)
        await db.commit()
        await db.refresh(category)
        return category

    async def delete_category(self, db: AsyncSession, category: Category) -> None:
        await db.delete(category)
        await db.commit()