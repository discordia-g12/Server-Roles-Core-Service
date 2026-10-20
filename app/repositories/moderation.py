import uuid
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Role
from app.models.role_assignment import RoleAssignment
from app.models.server_ban import ServerBan
from app.models.server_member import ServerMember
from app.models.server_mute import ServerMute
from app.repositories.outbox import add_outbox_event


class ModerationRepository:
    async def get_member(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> ServerMember | None:
        query = select(ServerMember).where(ServerMember.server_id == server_id, ServerMember.user_id == user_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_highest_role_position(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> int | None:
        query = (
            select(func.max(Role.position))
            .select_from(RoleAssignment)
            .join(Role, Role.id == RoleAssignment.role_id)
            .join(ServerMember, ServerMember.id == RoleAssignment.server_member_id)
            .where(ServerMember.server_id == server_id, ServerMember.user_id == user_id)
        )
        return await db.scalar(query)

    async def get_ban(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> ServerBan | None:
        query = select(ServerBan).where(ServerBan.server_id == server_id, ServerBan.user_id == user_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def list_bans(self, db: AsyncSession, server_id: uuid.UUID) -> list[ServerBan]:
        query = select(ServerBan).where(ServerBan.server_id == server_id).order_by(ServerBan.created_at.desc())
        result = await db.execute(query)
        return list(result.scalars().all())

    async def create_ban(
        self,
        db: AsyncSession,
        server_id: uuid.UUID,
        user_id: str,
        banned_by: str | None,
        reason: str | None,
    ) -> ServerBan:
        ban = ServerBan(
            server_id=server_id,
            user_id=user_id,
            banned_by=banned_by,
            reason=reason,
        )
        db.add(ban)

        member = await self.get_member(db, server_id, user_id)
        if member:
            await db.delete(member)

        add_outbox_event(
            db,
            "member.banned",
            {
                "server_id": str(server_id),
                "user_id": user_id,
                "banned_by": banned_by,
                "reason": reason,
            },
        )
        await db.commit()
        await db.refresh(ban)
        return ban

    async def remove_ban(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> bool:
        removed_id = await db.scalar(
            delete(ServerBan)
            .where(ServerBan.server_id == server_id, ServerBan.user_id == user_id)
            .returning(ServerBan.id)
        )
        if removed_id is None:
            return False

        add_outbox_event(
            db,
            "member.unbanned",
            {
                "server_id": str(server_id),
                "user_id": user_id,
            },
        )
        await db.commit()
        return True

    async def kick_member(
        self,
        db: AsyncSession,
        server_id: uuid.UUID,
        user_id: str,
        kicked_by: str | None,
        reason: str | None,
    ) -> bool:
        member_query = select(ServerMember).where(ServerMember.server_id == server_id, ServerMember.user_id == user_id)
        member = (await db.execute(member_query)).scalar_one_or_none()
        if not member:
            return False

        await db.delete(member)
        add_outbox_event(
            db,
            "member.kicked",
            {
                "server_id": str(server_id),
                "user_id": user_id,
                "kicked_by": kicked_by,
                "reason": reason,
            },
        )
        await db.commit()
        return True

    async def get_mute(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> ServerMute | None:
        query = select(ServerMute).where(ServerMute.server_id == server_id, ServerMute.user_id == user_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def create_or_update_mute(
        self,
        db: AsyncSession,
        server_id: uuid.UUID,
        user_id: str,
        muted_by: str | None,
        expires_at: datetime | None,
        reason: str | None,
    ) -> ServerMute:
        mute = await self.get_mute(db, server_id, user_id)
        if not mute:
            mute = ServerMute(
                server_id=server_id,
                user_id=user_id,
                muted_by=muted_by,
                expires_at=expires_at,
                reason=reason,
            )
            db.add(mute)
        else:
            mute.muted_by = muted_by
            mute.expires_at = expires_at
            mute.reason = reason

        add_outbox_event(
            db,
            "member.muted",
            {
                "server_id": str(server_id),
                "user_id": user_id,
                "muted_by": muted_by,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "reason": reason,
            },
        )
        await db.commit()
        await db.refresh(mute)
        return mute

    async def remove_mute(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> bool:
        mute = await self.get_mute(db, server_id, user_id)
        if not mute:
            return False

        await db.delete(mute)
        add_outbox_event(
            db,
            "member.unmuted",
            {
                "server_id": str(server_id),
                "user_id": user_id,
            },
        )
        await db.commit()
        return True

