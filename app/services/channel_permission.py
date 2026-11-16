import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import ALL_PERMISSIONS, Permission
from app.models.channel import Channel
from app.repositories.channel import ChannelRepository
from app.repositories.channel_permission import ChannelPermissionRepository
from app.repositories.role import RoleRepository
from app.schemas.channel_permission import ChannelRoleOverrideUpdate


class ChannelPermissionService:
    """Sobrescribir los permisos de un rol en un canal (#18).

    Gestionarlas pide lo mismo que editar los permisos de un rol: ser el dueño, ADMINISTRATOR o MANAGE_ROLES.
    La excepción vale solo en ese canal: los permisos generales del rol no cambian.
    """

    def __init__(
        self,
        repo: ChannelPermissionRepository | None = None,
        role_repo: RoleRepository | None = None,
        channel_repo: ChannelRepository | None = None,
    ):
        self.repo = repo or ChannelPermissionRepository()
        self.role_repo = role_repo or RoleRepository()
        self.channel_repo = channel_repo or ChannelRepository()

    async def _require_manage_permission(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> None:
        if not await self.role_repo.check_user_can_manage_roles(db, server_id, user_id):
            raise HTTPException(
                status_code=403, detail="You do not have permissions to manage channel permissions in this server."
            )

    async def _get_channel(self, db: AsyncSession, server_id: uuid.UUID, channel_id: uuid.UUID) -> Channel:
        channel = await self.channel_repo.get_channel_by_id(db, server_id, channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found.")
        return channel

    async def _require_role(self, db: AsyncSession, server_id: uuid.UUID, role_id: uuid.UUID) -> None:
        if not await self.role_repo.get_role_by_id(db, server_id, role_id):
            raise HTTPException(status_code=404, detail="Role not found.")

    async def list_role_overrides(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str, channel_id: uuid.UUID
    ):
        await self._require_manage_permission(db, server_id, user_id)
        await self._get_channel(db, server_id, channel_id)
        return await self.repo.get_role_overrides(db, channel_id)

    async def set_role_override(
        self,
        db: AsyncSession,
        server_id: uuid.UUID,
        user_id: str,
        channel_id: uuid.UUID,
        role_id: uuid.UUID,
        data: ChannelRoleOverrideUpdate,
    ):
        await self._require_manage_permission(db, server_id, user_id)
        channel = await self._get_channel(db, server_id, channel_id)
        await self._require_role(db, server_id, role_id)

        if (data.allow_bitmask | data.deny_bitmask) & ~ALL_PERMISSIONS:
            raise HTTPException(status_code=400, detail="Unknown permission bits.")
        # ADMINISTRATOR es de todo el servidor: un canal no lo puede dar ni quitar
        if (data.allow_bitmask | data.deny_bitmask) & Permission.ADMINISTRATOR.value:
            raise HTTPException(status_code=400, detail="ADMINISTRATOR cannot be overridden in a channel.")

        return await self.repo.upsert_role_override(
            db, channel, role_id, data.allow_bitmask, data.deny_bitmask, updated_by=user_id
        )

    async def delete_role_override(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str, channel_id: uuid.UUID, role_id: uuid.UUID
    ) -> None:
        await self._require_manage_permission(db, server_id, user_id)
        channel = await self._get_channel(db, server_id, channel_id)
        await self._require_role(db, server_id, role_id)

        override = await self.repo.get_role_override(db, channel_id, role_id)
        if not override:
            raise HTTPException(status_code=404, detail="This role has no permission override in this channel.")
        await self.repo.delete_role_override(db, channel, override, deleted_by=user_id)
