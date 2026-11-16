import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel
from app.models.channel_permission_override import ChannelPermissionOverride
from app.repositories.outbox import add_outbox_event


class ChannelPermissionRepository:
    """Excepciones de permisos de los roles en un canal (overrides). Las aplica ChannelAccessService."""

    async def get_role_overrides(self, db: AsyncSession, channel_id: uuid.UUID) -> list[ChannelPermissionOverride]:
        result = await db.execute(
            select(ChannelPermissionOverride).where(
                ChannelPermissionOverride.channel_id == channel_id,
                ChannelPermissionOverride.role_id.is_not(None),
            )
        )
        return list(result.scalars().all())

    async def get_role_override(
        self, db: AsyncSession, channel_id: uuid.UUID, role_id: uuid.UUID
    ) -> ChannelPermissionOverride | None:
        return await db.scalar(
            select(ChannelPermissionOverride).where(
                ChannelPermissionOverride.channel_id == channel_id,
                ChannelPermissionOverride.role_id == role_id,
            )
        )

    async def upsert_role_override(
        self,
        db: AsyncSession,
        channel: Channel,
        role_id: uuid.UUID,
        allow_bitmask: int,
        deny_bitmask: int,
        updated_by: str | None = None,
    ) -> ChannelPermissionOverride:
        override = await self.get_role_override(db, channel.id, role_id)
        old_allow = override.allow_bitmask if override else 0
        old_deny = override.deny_bitmask if override else 0
        if override is None:
            override = ChannelPermissionOverride(channel_id=channel.id, role_id=role_id)
        override.allow_bitmask = allow_bitmask
        override.deny_bitmask = deny_bitmask
        db.add(override)
        self._add_event(
            db, channel, role_id, old_allow, old_deny, allow_bitmask, deny_bitmask, updated_by
        )
        await db.commit()
        await db.refresh(override)
        return override

    async def delete_role_override(
        self,
        db: AsyncSession,
        channel: Channel,
        override: ChannelPermissionOverride,
        deleted_by: str | None = None,
    ) -> None:
        self._add_event(
            db, channel, override.role_id, override.allow_bitmask, override.deny_bitmask, 0, 0, deleted_by
        )
        await db.delete(override)
        await db.commit()

    @staticmethod
    def _add_event(
        db: AsyncSession,
        channel: Channel,
        role_id: uuid.UUID,
        old_allow: int,
        old_deny: int,
        new_allow: int,
        new_deny: int,
        updated_by: str | None,
    ) -> None:
        # Cambia lo que puede hacer el rol en este canal: Chat vuelve a chequear a quienes estén conectados
        add_outbox_event(
            db,
            "role.channel_permissions_updated",
            {
                "server_id": str(channel.server_id),
                "channel_id": str(channel.id),
                "channel_name": channel.name,
                "role_id": str(role_id),
                "old_allow_bitmask": old_allow,
                "old_deny_bitmask": old_deny,
                "new_allow_bitmask": new_allow,
                "new_deny_bitmask": new_deny,
                "updated_by": updated_by,
            },
        )
