import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission
from app.models.role import Role
from app.models.role_assignment import RoleAssignment
from app.models.server import Server
from app.models.server_member import ServerMember
from app.repositories.moderation import ModerationRepository


class ModerationService:
    def __init__(self, repo: ModerationRepository | None = None):
        self.repo = repo or ModerationRepository()

    async def _get_server(self, db: AsyncSession, server_id: uuid.UUID) -> Server:
        server = await db.scalar(select(Server).where(Server.id == server_id))
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")
        return server

    async def _require_permission(
        self, db: AsyncSession, server: Server, user_id: str, required_permission: Permission
    ) -> None:
        if server.owner_id == user_id:
            return

        query = (
            select(Role.permissions_bitmask)
            .join(RoleAssignment, RoleAssignment.role_id == Role.id)
            .join(ServerMember, ServerMember.id == RoleAssignment.server_member_id)
            .where(
                ServerMember.server_id == server.id,
                ServerMember.user_id == user_id,
            )
        )
        result = await db.execute(query)
        bitmasks = result.scalars().all()

        required_bits = Permission.ADMINISTRATOR.value | required_permission.value
        for mask in bitmasks:
            if (mask & required_bits) != 0:
                return

        raise HTTPException(
            status_code=403,
            detail=f"Missing required permission: {required_permission.name}",
        )

    async def ban_member(
        self,
        db: AsyncSession,
        server_id: uuid.UUID,
        user_id: str,
        target_user_id: str,
        reason: str | None = None,
    ):
        server = await self._get_server(db, server_id)
        if target_user_id == server.owner_id:
            raise HTTPException(status_code=400, detail="Cannot ban the server owner")
        if target_user_id == user_id:
            raise HTTPException(status_code=400, detail="Cannot ban yourself")

        await self._require_permission(db, server, user_id, Permission.BAN_MEMBERS)
        return await self.repo.create_ban(db, server_id, target_user_id, banned_by=user_id, reason=reason)

    async def unban_member(
        self,
        db: AsyncSession,
        server_id: uuid.UUID,
        user_id: str,
        target_user_id: str,
    ):
        server = await self._get_server(db, server_id)
        await self._require_permission(db, server, user_id, Permission.BAN_MEMBERS)
        removed = await self.repo.remove_ban(db, server_id, target_user_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Ban not found")

    async def list_bans(self, db: AsyncSession, server_id: uuid.UUID, user_id: str):
        server = await self._get_server(db, server_id)
        await self._require_permission(db, server, user_id, Permission.BAN_MEMBERS)
        return await self.repo.list_bans(db, server_id)

    async def kick_member(
        self,
        db: AsyncSession,
        server_id: uuid.UUID,
        user_id: str,
        target_user_id: str,
        reason: str | None = None,
    ):
        server = await self._get_server(db, server_id)
        if target_user_id == server.owner_id:
            raise HTTPException(status_code=400, detail="Cannot kick the server owner")
        if target_user_id == user_id:
            raise HTTPException(status_code=400, detail="Cannot kick yourself")

        await self._require_permission(db, server, user_id, Permission.KICK_MEMBERS)
        kicked = await self.repo.kick_member(db, server_id, target_user_id, kicked_by=user_id, reason=reason)
        if not kicked:
            raise HTTPException(status_code=404, detail="Member not found in this server")

    async def mute_member(
        self,
        db: AsyncSession,
        server_id: uuid.UUID,
        user_id: str,
        target_user_id: str,
        duration_seconds: int | None = None,
        reason: str | None = None,
    ):
        server = await self._get_server(db, server_id)
        if target_user_id == server.owner_id:
            raise HTTPException(status_code=400, detail="Cannot mute the server owner")
        if target_user_id == user_id:
            raise HTTPException(status_code=400, detail="Cannot mute yourself")

        await self._require_permission(db, server, user_id, Permission.MUTE_MEMBERS)
        expires_at = None
        if duration_seconds and duration_seconds > 0:
            expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=duration_seconds)

        return await self.repo.create_or_update_mute(
            db, server_id, target_user_id, muted_by=user_id, expires_at=expires_at, reason=reason
        )

    async def unmute_member(
        self,
        db: AsyncSession,
        server_id: uuid.UUID,
        user_id: str,
        target_user_id: str,
    ):
        server = await self._get_server(db, server_id)
        await self._require_permission(db, server, user_id, Permission.MUTE_MEMBERS)
        removed = await self.repo.remove_mute(db, server_id, target_user_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Mute not found")

