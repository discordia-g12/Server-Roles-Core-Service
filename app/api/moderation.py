import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.api.guards import reject_suspended_server
from app.db.session import get_db
from app.schemas.moderation import BanCreate, BanResponse, MuteCreate, MuteResponse
from app.services.moderation import ModerationService

router = APIRouter(prefix="/api/v1", tags=["moderation"], dependencies=[Depends(reject_suspended_server)])


@router.post("/servers/{server_id}/bans", response_model=BanResponse, status_code=status.HTTP_201_CREATED)
async def ban_member_endpoint(
    server_id: uuid.UUID,
    ban_data: BanCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ModerationService()
    return await service.ban_member(
        db, server_id, user_id, ban_data.user_id, ban_data.reason
    )


@router.get("/servers/{server_id}/bans", response_model=list[BanResponse], status_code=status.HTTP_200_OK)
async def list_bans_endpoint(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ModerationService()
    return await service.list_bans(db, server_id, user_id)


@router.delete("/servers/{server_id}/bans/{target_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unban_member_endpoint(
    server_id: uuid.UUID,
    target_user_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ModerationService()
    await service.unban_member(db, server_id, user_id, target_user_id)


@router.delete("/servers/{server_id}/members/{target_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def kick_member_endpoint(
    server_id: uuid.UUID,
    target_user_id: str,
    reason: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ModerationService()
    await service.kick_member(db, server_id, user_id, target_user_id, reason)


@router.post("/servers/{server_id}/mutes", response_model=MuteResponse, status_code=status.HTTP_201_CREATED)
async def mute_member_endpoint(
    server_id: uuid.UUID,
    mute_data: MuteCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ModerationService()
    return await service.mute_member(
        db, server_id, user_id, mute_data.user_id, mute_data.duration_seconds, mute_data.reason
    )


@router.delete("/servers/{server_id}/mutes/{target_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unmute_member_endpoint(
    server_id: uuid.UUID,
    target_user_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ModerationService()
    await service.unmute_member(db, server_id, user_id, target_user_id)

