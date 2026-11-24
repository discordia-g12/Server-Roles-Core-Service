import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import ALL_PERMISSIONS, Permission, effective_channel_permissions
from app.exceptions import ServerSuspendedError
from app.models.server import Server
from app.repositories.channel_access import ChannelAccessRepository
from app.repositories.server import ServerRepository
from app.schemas.internal import (
    CanConnectResponse,
    CanSendResponse,
    ChannelAccessResponse,
    ChannelViewersResponse,
    ServerPermissionsResponse,
    VisibleChannelsResponse,
)


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

        # Servidor suspendido por el staff (ADR-002): nadie lo usa, ni el dueño. Cubre chat, historial y voz
        if await self.repo.is_server_suspended(db, server_id):
            raise ServerSuspendedError()

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

    async def filter_channel_viewers(
        self, db: AsyncSession, channel_id: uuid.UUID, user_ids: list[str]
    ) -> ChannelViewersResponse:
        """Subconjunto de `user_ids` que puede ver el canal: la misma regla que da 403 en /access (miembro,
        no baneado y VIEW_CHANNELS con roles y overrides), en un número fijo de consultas.

        404 si el canal no existe. Notification lo usa para no mandar previews de canales privados.
        """
        channel = await self.repo.get_channel(db, channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        server_id = channel.server_id
        if await self.repo.is_server_suspended(db, server_id):
            raise ServerSuspendedError()

        user_ids = list(dict.fromkeys(user_ids))
        banned = await self.repo.get_banned_user_ids(db, server_id, user_ids)
        members = await self.repo.get_members_by_user_ids(db, server_id, [u for u in user_ids if u not in banned])
        if not members:
            return ChannelViewersResponse(user_ids=[])

        owner_id = await self.repo.get_owner_id(db, server_id)
        member_ids = [member_id for member_id, _ in members]
        roles_by_member = defaultdict(list)
        for member_id, role_id, bitmask in await self.repo.get_roles_for_members(db, member_ids):
            roles_by_member[member_id].append((role_id, bitmask))
        role_ids = list({role_id for roles in roles_by_member.values() for role_id, _ in roles})
        overrides = await self.repo.get_channel_overrides_for_members(db, channel_id, member_ids, role_ids)

        viewers = []
        for member_id, user_id in members:
            if user_id != owner_id:
                roles = roles_by_member[member_id]
                own_role_ids = {role_id for role_id, _ in roles}
                permissions = effective_channel_permissions(
                    role_bitmasks=[bitmask for _, bitmask in roles],
                    role_overrides=[(o.allow_bitmask, o.deny_bitmask) for o in overrides if o.role_id in own_role_ids],
                    member_overrides=[
                        (o.allow_bitmask, o.deny_bitmask) for o in overrides if o.server_member_id == member_id
                    ],
                )
                if not permissions & Permission.VIEW_CHANNELS.value:
                    continue
            viewers.append(user_id)
        return ChannelViewersResponse(user_ids=viewers)

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

        Menciones: mencionar a @everyone o a un rol exige MENTION_EVERYONE. Sin ese permiso
        `mentionable_role_ids` va vacío y Chat guarda esas menciones como texto plano.
        """
        access = await self.resolve(db, channel_id, user_id)
        if not access.has(Permission.VIEW_CHANNELS):
            raise HTTPException(status_code=403, detail="User does not have permission to view this channel")

        has_send_permission = access.has(Permission.SEND_MESSAGES)
        mute = await self.repo.get_active_mute(db, access.server_id, user_id)

        muted_until = None
        if mute and mute.expires_at and has_send_permission:
            muted_until = to_utc_iso(mute.expires_at)

        can_mention_everyone = access.has(Permission.MENTION_EVERYONE)
        mentionable_role_ids = (
            await self.repo.get_mentionable_role_ids(db, access.server_id) if can_mention_everyone else []
        )
        can_manage_messages = access.has(Permission.MANAGE_MESSAGES)
        can_add_reactions = access.has(Permission.ADD_REACTIONS)

        return ChannelAccessResponse(
            server_id=str(access.server_id),
            can_send=has_send_permission and mute is None,
            muted_until=muted_until,
            can_mention_everyone=can_mention_everyone,
            mentionable_role_ids=[str(role_id) for role_id in mentionable_role_ids],
            can_manage_messages=can_manage_messages,
            can_add_reactions=can_add_reactions,
        )

    async def get_welcome_channel_id(
        self, db: AsyncSession, server_id: uuid.UUID, default_role_bitmask: int, default_role_id: uuid.UUID
    ) -> uuid.UUID | None:
        """Canal donde se avisa que alguien se unió: el primer canal de texto de la barra lateral que el rol
        por defecto (@everyone) puede ver, así lo ven el que llega y todos los miembros. None si no hay."""
        channels = await self.repo.get_text_channels_in_sidebar_order(db, server_id)
        overrides = defaultdict(list)
        for override in await self.repo.get_role_overrides_for_channels(
            db, [channel.id for channel in channels], default_role_id
        ):
            overrides[override.channel_id].append((override.allow_bitmask, override.deny_bitmask))
        for channel in channels:
            permissions = effective_channel_permissions(
                role_bitmasks=[default_role_bitmask], role_overrides=overrides[channel.id], member_overrides=[]
            )
            if permissions & Permission.VIEW_CHANNELS.value:
                return channel.id
        return None

    async def get_visible_text_channels(
        self, db: AsyncSession, user_id: str, server_id: uuid.UUID | None = None
    ) -> VisibleChannelsResponse:
        """Canales de texto que el usuario puede ver (VIEW_CHANNELS) en todos sus servidores, o solo en
        `server_id` si viene.

        Chat lo usa para los no leídos y para la búsqueda de mensajes: así lee solo los canales que el usuario
        puede ver, sin confiar en la lista que mande el cliente. Un baneado deja de ser miembro, así que su
        servidor no aparece. `role_ids` son sus roles (sin los por defecto), para contar las menciones de rol.
        """
        # Los canales de un servidor suspendido no se leen, así que tampoco cuentan para no leídos ni búsquedas
        servers = [
            s
            for s in await ServerRepository().get_user_servers(db, user_id)
            if not s.is_suspended and (server_id is None or s.id == server_id)
        ]
        await self.attach_my_permissions(db, servers, user_id)
        role_ids = await self.repo.get_user_role_ids(db, user_id)
        return VisibleChannelsResponse(
            channel_ids=[
                str(channel.id)
                for server in servers
                for channel in server.channels
                if channel.type == "text" and channel.my_permissions & Permission.VIEW_CHANNELS.value
            ],
            role_ids=[str(role_id) for role_id in role_ids],
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

    async def get_server_permissions(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str
    ) -> ServerPermissionsResponse:
        owner_id = await self.repo.get_owner_id(db, server_id)
        if owner_id is None:
            raise HTTPException(status_code=404, detail="Server not found")

        # Servidor suspendido por el staff (ADR-002): tampoco se ve su registro de auditoría, ni siquiera el dueño
        if await self.repo.is_server_suspended(db, server_id):
            raise ServerSuspendedError()

        if owner_id == user_id:
            return ServerPermissionsResponse(
                server_id=str(server_id),
                user_id=user_id,
                is_owner=True,
                can_moderate=True,
                permissions_bitmask=ALL_PERMISSIONS,
            )

        member = await self.repo.get_member(db, server_id, user_id)
        if not member:
            raise HTTPException(status_code=403, detail="User is not a member of this server")

        roles = await self.repo.get_member_roles(db, member.id)
        role_bitmasks = [bitmask for _, bitmask in roles]
        permissions_bitmask = effective_channel_permissions(
            role_bitmasks=role_bitmasks, role_overrides=[], member_overrides=[]
        )
        moderation_bits = (
            Permission.ADMINISTRATOR.value
            | Permission.MANAGE_SERVER.value
            | Permission.BAN_MEMBERS.value
            | Permission.KICK_MEMBERS.value
            | Permission.MUTE_MEMBERS.value
            | Permission.VIEW_AUDIT_LOG.value
        )
        can_moderate = bool(permissions_bitmask & moderation_bits)
        return ServerPermissionsResponse(
            server_id=str(server_id),
            user_id=user_id,
            is_owner=False,
            can_moderate=can_moderate,
            permissions_bitmask=permissions_bitmask,
        )

