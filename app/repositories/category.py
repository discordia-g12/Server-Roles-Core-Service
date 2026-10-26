from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.repositories.outbox import add_outbox_event


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

    async def create_category(self, db: AsyncSession, server_id: uuid.UUID, name: str) -> Category:
        position = await self.get_next_position(db, server_id)
        category = Category(server_id=server_id, name=name, position=position)
        db.add(category)
        await db.flush() 
        add_outbox_event(db, "category.created", {"server_id": str(server_id), "category_id": str(category.id)})
        await db.commit()
        await db.refresh(category)
        return category

    async def update_category(self, db: AsyncSession, category: Category, update_data: dict) -> Category:
        for key, value in update_data.items():
            setattr(category, key, value)
        add_outbox_event(
            db, "category.updated", {"server_id": str(category.server_id), "category_id": str(category.id)}
        )
        await db.commit()
        await db.refresh(category)
        return category

    async def reorder_categories(self, db: AsyncSession, ordered: list[Category]) -> list[Category]:
        for position, category in enumerate(ordered):
            category.position = position
        if ordered:
            add_outbox_event(db, "categories.reordered", {"server_id": str(ordered[0].server_id)})
        await db.commit()
        return ordered

    async def delete_category(self, db: AsyncSession, category: Category) -> None:
        add_outbox_event(
            db, "category.deleted", {"server_id": str(category.server_id), "category_id": str(category.id)}
        )
        await db.delete(category)
        await db.commit()