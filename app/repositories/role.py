import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import DEFAULT_ROLE_PERMISSIONS, Permission
from app.models.role import Role
from app.models.role_assignment import RoleAssignment
from app.models.server import Server
from app.models.server_member import ServerMember
from app.repositories.outbox import add_outbox_event


class RoleRepository:
    async def get_roles_by_server(self, db: AsyncSession, server_id: uuid.UUID) -> list[Role]:
        query = select(Role).where(Role.server_id == server_id).order_by(Role.position)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def is_member(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> bool:
        member_id = await db.scalar(
            select(ServerMember.id).where(ServerMember.server_id == server_id, ServerMember.user_id == user_id)
        )
        return member_id is not None

    async def get_next_position(self, db: AsyncSession, server_id: uuid.UUID) -> int:
        query = select(func.max(Role.position)).where(Role.server_id == server_id)
        result = await db.execute(query)
        max_pos = result.scalar()
        return (max_pos + 1) if max_pos is not None else 0

    async def create_role(self, db: AsyncSession, server_id: uuid.UUID, name: str, color: str | None) -> Role:
        position = await self.get_next_position(db, server_id)
        role = Role(
            server_id=server_id,
            name=name,
            color=color,
            position=position,
            permissions_bitmask=int(DEFAULT_ROLE_PERMISSIONS),
            is_default=False,
        )
        db.add(role)
        await db.commit()
        await db.refresh(role)
        return role

    async def check_user_can_manage_roles(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> bool:
        server = await db.scalar(select(Server).where(Server.id == server_id))
        if not server:
            return False
        if server.owner_id == user_id:
            return True

        query = (
            select(Role.permissions_bitmask)
            .join(RoleAssignment, RoleAssignment.role_id == Role.id)
            .join(ServerMember, ServerMember.id == RoleAssignment.server_member_id)
            .where(ServerMember.server_id == server_id, ServerMember.user_id == user_id)
        )
        result = await db.execute(query)
        bitmasks = result.scalars().all()

        required_bits = Permission.ADMINISTRATOR | Permission.MANAGE_ROLES

        for bitmask in bitmasks:
            if (bitmask & required_bits.value) != 0:
                return True

        return False

    async def get_role_by_id(self, db: AsyncSession, server_id: uuid.UUID, role_id: uuid.UUID) -> Role | None:
        query = select(Role).where(Role.server_id == server_id, Role.id == role_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def delete_role(self, db: AsyncSession, role: Role) -> None:
        add_outbox_event(db, "role.deleted", {"server_id": str(role.server_id), "role_id": str(role.id)})
        await db.delete(role)
        await db.commit()

    async def update_role_permissions(self, db: AsyncSession, role: Role, new_permissions_bitmask: int) -> Role:
        role.permissions_bitmask = new_permissions_bitmask
        db.add(role)
        add_outbox_event(
            db,
            "role.permissions_updated",
            {
                "server_id": str(role.server_id),
                "role_id": str(role.id),
                "permissions_bitmask": new_permissions_bitmask,
            },
        )
        await db.commit()
        await db.refresh(role)
        return role

    async def user_has_role(self, db: AsyncSession, server_id: uuid.UUID, user_id: str, role_id: uuid.UUID) -> bool:
        query = (
            select(func.count())
            .select_from(RoleAssignment)
            .join(ServerMember, ServerMember.id == RoleAssignment.server_member_id)
            .where(
                ServerMember.server_id == server_id, ServerMember.user_id == user_id, RoleAssignment.role_id == role_id
            )
        )
        result = await db.execute(query)
        count = result.scalar()
        return count > 0

    async def get_members_by_role(
        self, db: AsyncSession, server_id: uuid.UUID, role_id: uuid.UUID
    ) -> list[ServerMember]:
        query = (
            select(ServerMember)
            .join(RoleAssignment, RoleAssignment.server_member_id == ServerMember.id)
            .where(ServerMember.server_id == server_id, RoleAssignment.role_id == role_id)
        )
        result = await db.execute(query)
        return result.scalars().all()

    async def get_member_by_user_id(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> ServerMember | None:
        query = select(ServerMember).where(ServerMember.server_id == server_id, ServerMember.user_id == user_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def assign_role(
        self,
        db: AsyncSession,
        server_member_id: uuid.UUID,
        role_id: uuid.UUID,
        server_id: uuid.UUID | None = None,
        user_id: str | None = None,
    ) -> None:
        already_assigned = await db.scalar(
            select(func.count())
            .select_from(RoleAssignment)
            .where(
                RoleAssignment.server_member_id == server_member_id,
                RoleAssignment.role_id == role_id,
            )
        )
        if already_assigned:
            return

        if not server_id or not user_id:
            member = await db.scalar(select(ServerMember).where(ServerMember.id == server_member_id))
            if member:
                server_id = member.server_id
                user_id = member.user_id

        assignment = RoleAssignment(server_member_id=server_member_id, role_id=role_id)
        db.add(assignment)
        if server_id and user_id:
            add_outbox_event(
                db,
                "member.role_assigned",
                {
                    "server_id": str(server_id),
                    "user_id": user_id,
                    "role_id": str(role_id),
                },
            )
        await db.commit()

    async def remove_role_assignment(
        self,
        db: AsyncSession,
        server_member_id: uuid.UUID,
        role_id: uuid.UUID,
        server_id: uuid.UUID | None = None,
        user_id: str | None = None,
    ) -> bool:
        query = select(RoleAssignment).where(
            RoleAssignment.server_member_id == server_member_id,
            RoleAssignment.role_id == role_id,
        )
        result = await db.execute(query)
        assignment = result.scalar_one_or_none()
        if not assignment:
            return False

        if not server_id or not user_id:
            member = await db.scalar(select(ServerMember).where(ServerMember.id == server_member_id))
            if member:
                server_id = member.server_id
                user_id = member.user_id

        if server_id and user_id:
            add_outbox_event(
                db,
                "member.role_removed",
                {
                    "server_id": str(server_id),
                    "user_id": user_id,
                    "role_id": str(role_id),
                },
            )

        await db.delete(assignment)
        await db.commit()
        return True

    async def set_default_role(self, db: AsyncSession, server_id: uuid.UUID, role: Role) -> Role:
        previous_default = await db.scalar(select(Role).where(Role.server_id == server_id, Role.is_default.is_(True)))
        if previous_default and previous_default.id != role.id:
            previous_default.is_default = False
            db.add(previous_default)

        role.is_default = True
        db.add(role)
        await db.commit()
        await db.refresh(role)
        return role

    async def update_role(self, db: AsyncSession, role: Role, name: str | None, color: str | None) -> Role:
        if name is not None:
            role.name = name
        if color is not None:
            role.color = color
        db.add(role)
        await db.commit()
        await db.refresh(role)
        return role

    async def get_highest_role_position(self, db: AsyncSession, server_id: uuid.UUID, user_id: str) -> int | None:
        query = (
            select(func.max(Role.position))
            .select_from(RoleAssignment)
            .join(Role, Role.id == RoleAssignment.role_id)
            .join(ServerMember, ServerMember.id == RoleAssignment.server_member_id)
            .where(ServerMember.server_id == server_id, ServerMember.user_id == user_id)
        )
        return await db.scalar(query)

    async def reorder_roles(self, db: AsyncSession, server_id: uuid.UUID, ordered_roles: list[Role]) -> list[Role]:
        for position, role in enumerate(ordered_roles):
            role.position = position
            db.add(role)
        add_outbox_event(db, "roles.reordered", {"server_id": str(server_id)})
        await db.commit()
        for role in ordered_roles:
            await db.refresh(role)
        return ordered_roles
