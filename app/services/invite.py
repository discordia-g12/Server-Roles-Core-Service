import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission
from app.models.role_assignment import RoleAssignment
from app.models.server_invite import ServerInvite
from app.models.server_member import ServerMember
from app.repositories.invite import InviteRepository

MAX_RETRIES_CODE = 3
class InviteService:
    def __init__(self, repository: InviteRepository):
        self.repository = repository

    async def _require_invite_permission(self, db: AsyncSession, server_id: uuid.UUID, user_id: str):
        """
        Validates whether the user has permission to manage invites for the given server.
        
        Args:
            db (AsyncSession): The database session.
            server_id (uuid.UUID): The ID of the server.
            user_id (str): The ID of the user.
            
        Raises:
            HTTPException: If the server is not found or the user lacks permissions.
        """
        server = await self.repository.get_server(db, server_id)
        if not server:
            raise HTTPException(status_code=404, detail="Server not found.")
        if server.owner_id == user_id:
            return
            
        bitmasks = await self.repository.get_user_permissions_bitmasks(db, server_id, user_id)
        
        required_bits = Permission.ADMINISTRATOR.value | Permission.CREATE_INVITE.value
        has_permission = any((bitmask & required_bits) != 0 for bitmask in bitmasks)
        
        if not has_permission:
            raise HTTPException(
                status_code=403, 
                detail="Insufficient permissions."
            )

    async def create_invite(
        self, 
        db: AsyncSession, 
        server_id: uuid.UUID, 
        user_id: str, 
        max_uses: int | None, 
        expires_in_seconds: int | None
    ):
        """
        Creates a new server invite.
        
        Args:
            db (AsyncSession): The database session.
            server_id (uuid.UUID): The ID of the server.
            user_id (str): The ID of the user creating the invite.
            max_uses (int | None): The maximum number of times the invite can be used.
            expires_in_seconds (int | None): The expiration time in seconds from now.
            
        Returns:
            ServerInvite: The newly created invite.
        """
        await self._require_invite_permission(db, server_id, user_id)
        
        expires_at = (
            datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=expires_in_seconds)
            if expires_in_seconds else None
        )
        
        for attempt in range(MAX_RETRIES_CODE):
            code = secrets.token_urlsafe(8)
            invite = ServerInvite(
                code=code,
                server_id=server_id,
                inviter_id=user_id,
                max_uses=max_uses,
                expires_at=expires_at
            )
            
            try:
                # Use nested transaction (savepoint) for retry logic
                async with db.begin_nested():
                    await self.repository.create_invite(db, invite)
                break  # Success
            except IntegrityError:
                if attempt == MAX_RETRIES_CODE - 1:
                    raise HTTPException(status_code=500, detail="Failed to generate a unique invite code.")
                continue

        await db.commit()
        await db.refresh(invite)
        return invite

    async def validate_and_use_invite(self, db: AsyncSession, code: str):
        """
        Validates an invite code and increments its usage count if valid.
        
        Args:
            db (AsyncSession): The database session.
            code (str): The invite code to validate.
            
        Returns:
            ServerInvite: The valid invite object.
            
        Raises:
            HTTPException: If the invite is invalid, expired, or has reached its usage limit.
        """
        invite = await self.repository.get_invite_by_code(db, code)
        
        if not invite or invite.is_revoked:
            raise HTTPException(status_code=400, detail="The invite is no longer valid.")
            
        if invite.expires_at and datetime.now(UTC).replace(tzinfo=None) > invite.expires_at:
            raise HTTPException(status_code=400, detail="The invitation has expired.")
            
        updated_invite = await self.repository.atomic_increment_uses(db, code)
        if not updated_invite:
            raise HTTPException(status_code=400, detail="The invitation exceeded the usage limit.")
            
        await db.commit()
        return updated_invite


    async def get_invite_preview(self, db: AsyncSession, code: str):
        
        invite = await self.repository.get_invite_by_code(db, code)
        if not invite or invite.is_revoked:
            raise HTTPException(status_code=404, detail="Invite not found or revoked")
            
        server = await self.repository.get_server(db, invite.server_id)
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")
            
        member_count_query = select(func.count()).select_from(ServerMember).where(ServerMember.server_id == server.id)
        member_count = await db.scalar(member_count_query)
        
        return {
            "code": invite.code,
            "server_id": invite.server_id,
            "server_name": server.name,
            "server_description": getattr(server, 'description', None),
            "server_icon": server.icon_url,
            "member_count": member_count or 0
        }

    async def join_server(self, db: AsyncSession, user_id: str, code: str) -> uuid.UUID:
        """
        Allows a user to join a server using an invite code.
        
        Args:
            db (AsyncSession): The database session.
            user_id (str): The ID of the user joining the server.
            code (str): The invite code being used.
            
        Returns:
            uuid.UUID: The ID of the server joined.
        """
        invite_preview = await self.repository.get_invite_by_code(db, code)
        if invite_preview and await self.repository.is_user_banned(db, invite_preview.server_id, user_id):
            raise HTTPException(status_code=403, detail="You are banned from this server.")

        invite = await self.validate_and_use_invite(db, code)

        existing = await self.repository.get_server_member(db, invite.server_id, user_id)
        if existing:
            return invite.server_id

        member = ServerMember(server_id=invite.server_id, user_id=user_id)
        await self.repository.create_server_member(db, member)

        default_role = await self.repository.get_default_role(db, invite.server_id)
        if default_role:
            await self.repository.assign_role(db, RoleAssignment(server_member_id=member.id, role_id=default_role.id))

        await db.commit()
        return invite.server_id

    async def revoke_invite(self, db: AsyncSession, server_id: uuid.UUID, user_id: str, code: str):
        """
        Revokes an active server invite manually.
        
        Args:
            db (AsyncSession): The database session.
            server_id (uuid.UUID): The ID of the server.
            user_id (str): The ID of the user performing the revocation.
            code (str): The invite code to revoke.
            
        Raises:
            HTTPException: If the invite is not found or the user lacks permissions.
        """
        await self._require_invite_permission(db, server_id, user_id)
        invite = await self.repository.get_invite_by_code_and_server(db, code, server_id)
        
        if not invite:
            raise HTTPException(status_code=404, detail="Invite not found.")
            
        invite.is_revoked = True
        await db.commit()
