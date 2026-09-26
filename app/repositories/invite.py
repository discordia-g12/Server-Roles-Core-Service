import uuid

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Role
from app.models.role_assignment import RoleAssignment
from app.models.server import Server
from app.models.server_ban import ServerBan
from app.models.server_invite import ServerInvite
from app.models.server_member import ServerMember


class InviteRepository:
    async def get_server(self, db: AsyncSession, server_id: uuid.UUID) -> Server | None:
        return await db.scalar(select(Server).where(Server.id == server_id))

    async def get_user_permissions_bitmasks(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> list[int]:
        query = (
            select(Role.permissions_bitmask)
            .join(RoleAssignment, RoleAssignment.role_id == Role.id)
            .join(ServerMember, ServerMember.id == RoleAssignment.server_member_id)
            .where(
                ServerMember.server_id == server_id,
                ServerMember.user_id == user_id
            )
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def create_invite(self, db: AsyncSession, invite: ServerInvite) -> ServerInvite:
        db.add(invite)
        await db.flush()
        return invite

    async def get_invite_by_code(self, db: AsyncSession, code: str) -> ServerInvite | None:
        return await db.scalar(select(ServerInvite).where(ServerInvite.code == code))

    async def get_invite_by_code_and_server(
        self, db: AsyncSession, code: str, server_id: uuid.UUID
    ) -> ServerInvite | None:
        return await db.scalar(
            select(ServerInvite).where(
                ServerInvite.code == code, 
                ServerInvite.server_id == server_id
            )
        )

    async def atomic_increment_uses(self, db: AsyncSession, code: str) -> ServerInvite | None:
        result = await db.execute(
            update(ServerInvite)
            .where(
                ServerInvite.code == code,
                or_(
                    ServerInvite.max_uses.is_(None),
                    ServerInvite.uses < ServerInvite.max_uses
                )
            )
            .values(uses=ServerInvite.uses + 1)
            .returning(ServerInvite)
        )
        return result.scalar_one_or_none()

    async def is_user_banned(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> bool:
        ban = await db.scalar(
            select(ServerBan).where(
                ServerBan.server_id == server_id, 
                ServerBan.user_id == user_id
            )
        )
        return ban is not None

    async def get_server_member(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> ServerMember | None:
        return await db.scalar(
            select(ServerMember).where(
                ServerMember.server_id == server_id,
                ServerMember.user_id == user_id
            )
        )

    async def create_server_member(self, db: AsyncSession, member: ServerMember) -> ServerMember:
        db.add(member)
        await db.flush()
        return member

    async def get_default_role(self, db: AsyncSession, server_id: uuid.UUID) -> Role | None:
        return await db.scalar(
            select(Role).where(
                Role.server_id == server_id,
                Role.is_default.is_(True)
            )
        )

    async def assign_role(self, db: AsyncSession, role_assignment: RoleAssignment):
        db.add(role_assignment)
