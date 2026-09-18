import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission
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

    async def update_role_permissions(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str, role_id: uuid.UUID, new_permissions_bitmask: int
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

        had_admin_before = (role.permissions_bitmask & Permission.ADMINISTRATOR.value) != 0
        has_admin_after = (new_permissions_bitmask & Permission.ADMINISTRATOR.value) != 0
        if had_admin_before and not has_admin_after:
            is_its_own_role =await self.repo.user_has_role(db, server_id, user_id, role_id)
            if is_its_own_role:
                raise HTTPException(
                    status_code=403,
                    detail="You cannot remove the ADMINISTRATOR permission from your own role"
                )
        await self.repo.update_role_permissions(db, role, new_permissions_bitmask)
        return role

    async def get_members_by_role(self, db: AsyncSession, server_id: uuid.UUID, user_id: str, role_id: uuid.UUID):
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
        return await self.repo.get_members_by_role(db, server_id, role_id)
