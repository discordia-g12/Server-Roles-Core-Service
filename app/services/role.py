import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission
from app.models.role import Role
from app.models.server_member import ServerMember
from app.repositories.role import RoleRepository
from app.schemas.role import RoleCreate, RoleUpdate


class RoleService:
    def __init__(self, repo: RoleRepository):
        self.repo = repo

    async def _require_manage_permission(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> None:
        has_permission = await self.repo.check_user_can_manage_roles(db, server_id, user_id)
        if not has_permission:
            raise HTTPException(
                status_code=403,
                detail="You do not have permissions to manage roles in this server."
            )

    async def _get_role(self, db: AsyncSession, server_id: uuid.UUID, role_id: uuid.UUID) -> Role:
        role = await self.repo.get_role_by_id(db, server_id, role_id)
        if not role:
            raise HTTPException(
                status_code=404,
                detail="Role not found."
            )
        return role

    async def _get_member(self, db: AsyncSession, server_id: uuid.UUID, target_user_id: str) -> ServerMember:
        member = await self.repo.get_member_by_user_id(db, server_id, target_user_id)
        if not member:
            raise HTTPException(
                status_code=404,
                detail="Member not found."
            )
        return member

    async def get_roles(self, db: AsyncSession, server_id: uuid.UUID, user_id: str):
        await self._require_manage_permission(db, server_id, user_id)
        return await self.repo.get_roles_by_server(db, server_id)

    async def create_role(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str, role_data: RoleCreate
    ):
        await self._require_manage_permission(db, server_id, user_id)
        return await self.repo.create_role(db, server_id, role_data.name, role_data.color)

    async def delete_role(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str, role_id: uuid.UUID
    ):
        await self._require_manage_permission(db, server_id, user_id)
        role = await self._get_role(db, server_id, role_id)

        if role.is_default:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete the default server role."
            )

        await self.repo.delete_role(db, role)

    async def update_role_permissions(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str, role_id: uuid.UUID, new_permissions_bitmask: int
    ):
        await self._require_manage_permission(db, server_id, user_id)
        role = await self._get_role(db, server_id, role_id)

        had_admin_before = (role.permissions_bitmask & Permission.ADMINISTRATOR.value) != 0
        has_admin_after = (new_permissions_bitmask & Permission.ADMINISTRATOR.value) != 0
        if had_admin_before and not has_admin_after:
            is_its_own_role = await self.repo.user_has_role(db, server_id, user_id, role_id)
            if is_its_own_role:
                raise HTTPException(
                    status_code=403,
                    detail="You cannot remove the ADMINISTRATOR permission from your own role"
                )
        await self.repo.update_role_permissions(db, role, new_permissions_bitmask)
        return role

    async def get_members_by_role(self, db: AsyncSession, server_id: uuid.UUID, user_id: str, role_id: uuid.UUID):
        await self._require_manage_permission(db, server_id, user_id)
        await self._get_role(db, server_id, role_id)
        return await self.repo.get_members_by_role(db, server_id, role_id)

    async def assign_role_to_member(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str, role_id: uuid.UUID, target_user_id: str
    ):
        await self._require_manage_permission(db, server_id, user_id)
        await self._get_role(db, server_id, role_id)
        member = await self._get_member(db, server_id, target_user_id)

        await self.repo.assign_role(db, member.id, role_id, server_id=server_id, user_id=target_user_id)

    async def remove_role_from_member(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str, role_id: uuid.UUID, target_user_id: str
    ):
        await self._require_manage_permission(db, server_id, user_id)
        await self._get_role(db, server_id, role_id)
        member = await self._get_member(db, server_id, target_user_id)

        removed = await self.repo.remove_role_assignment(
            db, member.id, role_id, server_id=server_id, user_id=target_user_id
        )
        if not removed:
            raise HTTPException(
                status_code=404,
                detail="Member does not have this role assigned."
            )

    async def set_default_role(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str, role_id: uuid.UUID
    ):
        await self._require_manage_permission(db, server_id, user_id)
        role = await self._get_role(db, server_id, role_id)
        return await self.repo.set_default_role(db, server_id, role)

    async def update_role(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str, role_id: uuid.UUID, update_data: RoleUpdate
    ):
        await self._require_manage_permission(db, server_id, user_id)
        role = await self._get_role(db, server_id, role_id)
        if role.is_default and update_data.name is not None and update_data.name != role.name:
            raise HTTPException(
                status_code=400,
                detail="Cannot change the name of the default server role."
            )
        return await self.repo.update_role(db, role, update_data.name, update_data.color)