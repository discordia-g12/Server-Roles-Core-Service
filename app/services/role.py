import uuid
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.role import RoleRepository
from app.schemas.role import RoleCreate

class RoleService:
    def __init__(self, repo: RoleRepository):
        self.repo = repo

    async def create_role(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str, role_data: RoleCreate
    ):
        has_permission = await self.repo.check_user_can_manage_roles(db, server_id, user_id)
        if not has_permission:
            raise HTTPException(
                status_code=403, 
                detail="You do not have permissions to manage roles in this server."
            )

        return await self.repo.create_role(db, server_id, role_data.name, role_data.color)

    async def delete_role(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str, role_id: uuid.UUID
    ):
        has_permission = await self.repo.check_user_can_manage_roles(db, server_id, user_id)
        if not has_permission:
            raise HTTPException(
                status_code=403, 
                detail="You do not have permissions to manage roles in this server."
            )

        role = await self.repo.get_role_by_id(db, server_id, role_id)
        if not role:
            raise HTTPException(
                status_code=404,
                detail="Role not found."
            )

        if role.is_default:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete the default server role."
            )

        await self.repo.delete_role(db, role)
