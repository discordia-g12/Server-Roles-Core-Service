import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import ALL_PERMISSIONS, Permission, effective_channel_permissions
from app.models.server import Server
from app.repositories.channel_access import ChannelAccessRepository
from app.schemas.internal import CanConnectResponse, CanSendResponse, ChannelAccessResponse


@dataclass
class ChannelAccess:
    server_id: uuid.UUID
    permissions: int

    def has(self, permission: Permission) -> bool:
        return (self.permissions & permission.value) != 0


def to_utc_iso(value: datetime) -> str:
    """expires_at se guarda en UTC sin zona: se devuelve con 'Z' para que nadie lo lea como hora local."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ChannelAccessService:
    """Qué puede hacer un usuario en un canal. Lo consultan Chat y Voice por /internal."""

    def __init__(self, repo: ChannelAccessRepository | None = None):
        self.repo = repo or ChannelAccessRepository()

    async def resolve(self, db: AsyncSession, channel_id: uuid.UUID, user_id: str) -> ChannelAccess:
        """Permisos efectivos del usuario en el canal.

        404 si el canal no existe; 403 si no es miembro o está baneado. El resto (mute, permiso puntual)
        lo decide cada caso de uso.
        """
        channel = await self.repo.get_channel(db, channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        server_id = channel.server_id

        member = await self.repo.get_member(db, server_id, user_id)
        if not member:
            raise HTTPException(status_code=403, detail="User is not a member of the server")

        if await self.repo.is_banned(db, server_id, user_id):
            raise HTTPException(status_code=403, detail="User is banned from the server")

        if await self.repo.get_owner_id(db, server_id) == user_id:
            return ChannelAccess(server_id=server_id, permissions=ALL_PERMISSIONS)

        roles = await self.repo.get_member_roles(db, member.id)
        role_ids = [role_id for role_id, _ in roles]
        overrides = await self.repo.get_channel_overrides(db, channel_id, member.id, role_ids)

        permissions = effective_channel_permissions(
            role_bitmasks=[bitmask for _, bitmask in roles],
            role_overrides=[(o.allow_bitmask, o.deny_bitmask) for o in overrides if o.role_id],
            member_overrides=[(o.allow_bitmask, o.deny_bitmask) for o in overrides if o.server_member_id],
        )
        return ChannelAccess(server_id=server_id, permissions=permissions)

    async def attach_my_permissions(self, db: AsyncSession, servers: list[Server], user_id: str) -> list[Server]:
        """Agrega a cada servidor y a cada uno de sus canales `my_permissions`: los permisos efectivos del
        usuario (en los canales, con sus overrides). El front los usa para mostrar solo lo que puede hacer;
        cada acción se sigue chequeando en su endpoint.
        """
        for server in servers:
            channels = list(server.channels)
            if server.owner_id == user_id:
                server.my_permissions = ALL_PERMISSIONS
                for channel in channels:
                    channel.my_permissions = ALL_PERMISSIONS
                continue

            member = await self.repo.get_member(db, server.id, user_id)
            if not member:
                server.my_permissions = 0
                for channel in channels:
                    channel.my_permissions = 0
                continue

            roles = await self.repo.get_member_roles(db, member.id)
            role_ids = [role_id for role_id, _ in roles]
            role_bitmasks = [bitmask for _, bitmask in roles]
            server.my_permissions = effective_channel_permissions(
                role_bitmasks=role_bitmasks, role_overrides=[], member_overrides=[]
            )

            overrides_by_channel = defaultdict(list)
            for override in await self.repo.get_overrides_for_channels(
                db, [channel.id for channel in channels], member.id, role_ids
            ):
                overrides_by_channel[override.channel_id].append(override)
            for channel in channels:
                overrides = overrides_by_channel[channel.id]
                channel.my_permissions = effective_channel_permissions(
                    role_bitmasks=role_bitmasks,
                    role_overrides=[(o.allow_bitmask, o.deny_bitmask) for o in overrides if o.role_id],
                    member_overrides=[(o.allow_bitmask, o.deny_bitmask) for o in overrides if o.server_member_id],
                )
        return servers

    async def get_text_channel_access(
        self, db: AsyncSession, channel_id: uuid.UUID, user_id: str
    ) -> ChannelAccessResponse:
        """Ver el canal y escribir en él son permisos distintos: un muteado ve pero no escribe.

        403 si no tiene VIEW_CHANNELS. `muted_until` solo se informa si el mute es lo único que le impide
        escribir, así quien lo recibe puede habilitarlo al vencer sin volver a preguntar.
        """
        access = await self.resolve(db, channel_id, user_id)
        if not access.has(Permission.VIEW_CHANNELS):
            raise HTTPException(status_code=403, detail="User does not have permission to view this channel")

        has_send_permission = access.has(Permission.SEND_MESSAGES)
        mute = await self.repo.get_active_mute(db, access.server_id, user_id)

        muted_until = None
        if mute and mute.expires_at and has_send_permission:
            muted_until = to_utc_iso(mute.expires_at)

        return ChannelAccessResponse(
            server_id=str(access.server_id),
            can_send=has_send_permission and mute is None,
            muted_until=muted_until,
        )

    async def check_can_send(self, db: AsyncSession, channel_id: uuid.UUID, user_id: str) -> CanSendResponse:
        """Deprecado (lo reemplaza get_text_channel_access): 403 si está muteado o no tiene SEND_MESSAGES."""
        access = await self.resolve(db, channel_id, user_id)
        # El mute aplica también al dueño y a los administradores
        if await self.repo.get_active_mute(db, access.server_id, user_id):
            raise HTTPException(status_code=403, detail="User is muted in the server")
        if not access.has(Permission.SEND_MESSAGES):
            raise HTTPException(
                status_code=403, detail="User does not have permission to send messages in this channel"
            )
        return CanSendResponse(server_id=str(access.server_id))

    async def check_can_connect(self, db: AsyncSession, channel_id: uuid.UUID, user_id: str) -> CanConnectResponse:
        access = await self.resolve(db, channel_id, user_id)
        if not access.has(Permission.CONNECT):
            raise HTTPException(
                status_code=403, detail="User does not have permission to connect to this voice channel"
            )
        # El mute aplica también al dueño y a los administradores (como en el chat)
        mute = await self.repo.get_active_mute(db, access.server_id, user_id)
        return CanConnectResponse(
            server_id=str(access.server_id),
            can_speak=access.has(Permission.SPEAK) and mute is None,
            can_video=access.has(Permission.VIDEO),
            can_screen_share=access.has(Permission.SCREEN_SHARE),
        )
