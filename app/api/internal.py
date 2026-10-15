import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.core.permissions import Permission
from app.db.session import get_db
from app.models.channel import Channel
from app.models.channel_permission_override import ChannelPermissionOverride
from app.models.role import Role
from app.models.role_assignment import RoleAssignment
from app.models.server import Server
from app.models.server_ban import ServerBan
from app.models.server_member import ServerMember
from app.models.server_mute import ServerMute

router = APIRouter(prefix="/internal", tags=["internal"])

@router.get("/channels/{channel_id}/can-send", status_code=200)
async def can_send_message(
    channel_id: uuid.UUID,
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    channel = await db.scalar(select(Channel).where(Channel.id == channel_id))
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
        
    server_id = channel.server_id
    
    member = await db.scalar(
        select(ServerMember).where(
            ServerMember.server_id == server_id, ServerMember.user_id == user_id
        )
    )
    if not member:
        raise HTTPException(status_code=403, detail="User is not a member of the server")
        
    ban = await db.scalar(
        select(ServerBan).where(
            ServerBan.server_id == server_id, ServerBan.user_id == user_id
        )
    )
    if ban:
        raise HTTPException(status_code=403, detail="User is banned from the server")
        
    now = func.now()
    mute = await db.scalar(
        select(ServerMute).where(
            ServerMute.server_id == server_id, 
            ServerMute.user_id == user_id,
            or_(ServerMute.expires_at.is_(None), ServerMute.expires_at > now)
        )
    )
    if mute:
        raise HTTPException(status_code=403, detail="User is muted in the server")
        
    server = await db.scalar(select(Server).where(Server.id == server_id))
    if server.owner_id == user_id:
        return {"can_send": True, "server_id": str(server_id)}
        
    roles = await db.execute(
        select(Role)
        .join(RoleAssignment, RoleAssignment.role_id == Role.id)
        .where(RoleAssignment.server_member_id == member.id)
    )
    roles = roles.scalars().all()
    
    base_permissions = 0
    role_ids = []
    for role in roles:
        base_permissions |= role.permissions_bitmask
        role_ids.append(role.id)
        
    if (base_permissions & Permission.ADMINISTRATOR.value) != 0:
        return {"can_send": True, "server_id": str(server_id)}
        
    conditions = [ChannelPermissionOverride.server_member_id == member.id]
    if role_ids:
        conditions.append(ChannelPermissionOverride.role_id.in_(role_ids))
        
    overrides = await db.execute(
        select(ChannelPermissionOverride).where(
            ChannelPermissionOverride.channel_id == channel_id,
            or_(*conditions)
        )
    )
    overrides = overrides.scalars().all()
    
    role_allow = 0
    role_deny = 0
    member_allow = 0
    member_deny = 0
    
    for override in overrides:
        if override.role_id:
            role_allow |= override.allow_bitmask
            role_deny |= override.deny_bitmask
        if override.server_member_id:
            member_allow |= override.allow_bitmask
            member_deny |= override.deny_bitmask
            
    effective = (base_permissions & ~role_deny) | role_allow
    effective = (effective & ~member_deny) | member_allow
    

    if (effective & Permission.SEND_MESSAGES.value) == 0:
        raise HTTPException(status_code=403, detail="User does not have permission to send messages in this channel")
        
    return {"can_send": True, "server_id": str(server_id)}


@router.get("/channels/{channel_id}/can-connect", status_code=200)
async def can_connect(
    channel_id: uuid.UUID,
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    channel = await db.scalar(select(Channel).where(Channel.id == channel_id))
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
        
    server_id = channel.server_id
    
    member = await db.scalar(
        select(ServerMember).where(
            ServerMember.server_id == server_id, ServerMember.user_id == user_id
        )
    )
    if not member:
        raise HTTPException(status_code=403, detail="User is not a member of the server")
        
    ban = await db.scalar(
        select(ServerBan).where(
            ServerBan.server_id == server_id, ServerBan.user_id == user_id
        )
    )
    if ban:
        raise HTTPException(status_code=403, detail="User is banned from the server")
        

    server = await db.scalar(select(Server).where(Server.id == server_id))
    if server.owner_id == user_id:
        return {"can_connect": True, "server_id": str(server_id)}
        
    roles = await db.execute(
        select(Role)
        .join(RoleAssignment, RoleAssignment.role_id == Role.id)
        .where(RoleAssignment.server_member_id == member.id)
    )
    roles = roles.scalars().all()
    
    base_permissions = 0
    role_ids = []
    for role in roles:
        base_permissions |= role.permissions_bitmask
        role_ids.append(role.id)
        
    if (base_permissions & Permission.ADMINISTRATOR.value) != 0:
        return {"can_connect": True, "server_id": str(server_id)}
        
    conditions = [ChannelPermissionOverride.server_member_id == member.id]
    if role_ids:
        conditions.append(ChannelPermissionOverride.role_id.in_(role_ids))
        
    overrides = await db.execute(
        select(ChannelPermissionOverride).where(
            ChannelPermissionOverride.channel_id == channel_id,
            or_(*conditions)
        )
    )
    overrides = overrides.scalars().all()
    
    role_allow = 0
    role_deny = 0
    member_allow = 0
    member_deny = 0
    
    for override in overrides:
        if override.role_id:
            role_allow |= override.allow_bitmask
            role_deny |= override.deny_bitmask
        if override.server_member_id:
            member_allow |= override.allow_bitmask
            member_deny |= override.deny_bitmask
            
    effective = (base_permissions & ~role_deny) | role_allow
    effective = (effective & ~member_deny) | member_allow
    
    if (effective & Permission.CONNECT.value) == 0:
        raise HTTPException(status_code=403, detail="User does not have permission to connect to this voice channel")
        
    return {"can_connect": True, "server_id": str(server_id)}