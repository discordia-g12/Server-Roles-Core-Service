import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.role import Role
from app.models.server import Server
from app.models.server_member import ServerMember
from app.models.role_assignment import RoleAssignment
from app.core.permissions import Permission, DEFAULT_ROLE_PERMISSIONS

class RoleRepository:
    async def get_next_position(self, db: AsyncSession, server_id: uuid.UUID) -> int:
        query = select(func.max(Role.position)).where(Role.server_id == server_id)
        result = await db.execute(query)
        max_pos = result.scalar()
        return (max_pos + 1) if max_pos is not None else 0

    async def create_role(
        self, db: AsyncSession, server_id: uuid.UUID, name: str, color: str | None
    ) -> Role:
        position = await self.get_next_position(db, server_id)
        role = Role(
            server_id=server_id,
            name=name,
            color=color,
            position=position,
            permissions_bitmask=int(DEFAULT_ROLE_PERMISSIONS),
            is_default=False
        )
        db.add(role)
        await db.commit()
        await db.refresh(role)
        return role

    async def check_user_can_manage_roles(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: str
    ) -> bool:
        server = await db.scalar(select(Server).where(Server.id == server_id))
        if not server:
            return False
        if server.owner_id == user_id:
            return True
            
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
        bitmasks = result.scalars().all()
        
        required_bits = Permission.ADMINISTRATOR | Permission.MANAGE_ROLES
        
        for bitmask in bitmasks:
            if (bitmask & required_bits.value) != 0:
                return True
                
        return False

    async def get_role_by_id(
        self, db: AsyncSession, server_id: uuid.UUID, role_id: uuid.UUID
    ) -> Role | None:
        query = select(Role).where(Role.server_id == server_id, Role.id == role_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def delete_role(self, db: AsyncSession, role: Role) -> None:
        await db.delete(role)
        await db.commit()
