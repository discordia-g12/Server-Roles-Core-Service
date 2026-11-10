import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.session import get_db
from app.repositories.category import CategoryRepository
from app.repositories.channel import ChannelRepository
from app.repositories.invite import InviteRepository
from app.repositories.role import RoleRepository
from app.repositories.server import ServerRepository
from app.schemas.category import CategoryCreate, CategoryReorder, CategoryResponse
from app.schemas.channel import ChannelCreate, ChannelReorder, ChannelResponse, ChannelUpdate
from app.schemas.invite import InviteCreate, InviteResponse
from app.schemas.role import (
    RoleCreate,
    RoleMemberResponse,
    RoleReorder,
    RoleResponse,
    RoleUpdate,
    RoleUpdatePermissions,
)
from app.schemas.server import (
    MemberGrowthResponse,
    MutualServerResponse,
    ServerCreate,
    ServerMemberPage,
    ServerResponse,
)
from app.schemas.server_transfer import ServerTransferCreate, ServerTransferResponse
from app.services.category import CategoryService
from app.services.channel import ChannelService
from app.services.invite import InviteService
from app.services.role import RoleService
from app.services.server import ServerService
from app.services.server_transfer import ServerTransferService

router = APIRouter(prefix="/api/v1", tags=["servers"])


@router.get("/servers", response_model=list[ServerResponse], status_code=200)
async def get_user_servers_endpoint(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ServerService(ServerRepository())
    return await service.get_user_servers(db, user_id)


# Va antes de las rutas /servers/{server_id}/...: "mutual" no es un id de servidor.
@router.get("/servers/mutual/{user_id}", response_model=list[MutualServerResponse], status_code=200)
async def get_mutual_servers_endpoint(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    viewer_id: str = Depends(get_current_user_id),
):
    """Servidores del usuario autenticado donde también está user_id (perfil público)."""
    service = ServerService(ServerRepository())
    return await service.get_mutual_servers(db, viewer_id, user_id)


@router.post("/servers", response_model=ServerResponse, status_code=201)
async def create_server_endpoint(
    name: str = Form(..., min_length=1, max_length=100, pattern=r"^[^\x00]+$"),
    icon: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    owner_id: str = Depends(get_current_user_id),
):
    server_data = ServerCreate(name=name)
    service = ServerService(ServerRepository())

    created_server = await service.create_server(db, owner_id=owner_id, server_name=server_data.name, icon=icon)
    return created_server


@router.put("/servers/{server_id}/icon", response_model=ServerResponse, status_code=200)
async def update_server_icon_endpoint(
    server_id: uuid.UUID,
    icon: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Reemplaza el ícono (multipart, campo "icon"). Devuelve el servidor con la URL nueva."""
    service = ServerService(ServerRepository())
    return await service.update_icon(db, server_id=server_id, user_id=user_id, icon=icon)


@router.delete("/servers/{server_id}/icon", response_model=ServerResponse, status_code=200)
async def remove_server_icon_endpoint(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Quita el ícono. Devuelve el servidor sin ícono."""
    service = ServerService(ServerRepository())
    return await service.remove_icon(db, server_id=server_id, user_id=user_id)


@router.get("/servers/{server_id}/members", response_model=ServerMemberPage, status_code=200)
async def get_server_members_endpoint(
    server_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ServerService(ServerRepository())
    return await service.get_server_members(db, server_id, user_id, limit, offset)


@router.post("/servers/{server_id}/channels", response_model=ChannelResponse, status_code=201)
async def create_channel_endpoint(
    server_id: uuid.UUID,
    channel_data: ChannelCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ChannelService(ChannelRepository())
    return await service.create_channel(db, server_id, user_id, channel_data)


@router.delete("/servers/{server_id}/channels/{channel_id}", status_code=204)
async def delete_channel_endpoint(
    server_id: uuid.UUID,
    channel_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ChannelService(ChannelRepository())
    await service.delete_channel(db, server_id, user_id, channel_id)


@router.patch("/servers/{server_id}/channels/{channel_id}", response_model=ChannelResponse, status_code=200)
async def update_channel_endpoint(
    server_id: uuid.UUID,
    channel_id: uuid.UUID,
    channel_data: ChannelUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ChannelService(ChannelRepository())
    return await service.update_channel(db, server_id, user_id, channel_id, channel_data)


@router.put("/servers/{server_id}/channels/order", response_model=list[ChannelResponse], status_code=200)
async def reorder_channels_endpoint(
    server_id: uuid.UUID,
    reorder: ChannelReorder,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ChannelService(ChannelRepository())
    return await service.reorder_channels(db, server_id, user_id, reorder)


@router.post("/servers/{server_id}/categories", response_model=CategoryResponse, status_code=201)
async def create_category_endpoint(
    server_id: uuid.UUID,
    category_data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = CategoryService(CategoryRepository())
    return await service.create_category(db, server_id, user_id, category_data)


@router.get("/servers/{server_id}/categories", response_model=list[CategoryResponse], status_code=200)
async def get_categories_endpoint(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = CategoryService(CategoryRepository())
    return await service.get_categories(db, server_id, user_id)


@router.delete("/servers/{server_id}/categories/{category_id}", status_code=204)
async def delete_category_endpoint(
    server_id: uuid.UUID,
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = CategoryService(CategoryRepository())
    await service.delete_category(db, server_id, user_id, category_id)


@router.put("/servers/{server_id}/categories/order", response_model=list[CategoryResponse], status_code=200)
async def reorder_categories_endpoint(
    server_id: uuid.UUID,
    reorder: CategoryReorder,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = CategoryService(CategoryRepository())
    return await service.reorder_categories(db, server_id, user_id, reorder)


@router.get("/servers/{server_id}/roles", response_model=list[RoleResponse], status_code=200)
async def get_roles_endpoint(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = RoleService(RoleRepository())
    return await service.get_roles(db, server_id, user_id)


@router.post("/servers/{server_id}/roles", response_model=RoleResponse, status_code=201)
async def create_role_endpoint(
    server_id: uuid.UUID,
    role_data: RoleCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = RoleService(RoleRepository())
    return await service.create_role(db, server_id, user_id, role_data)


@router.put("/servers/{server_id}/roles/order", response_model=list[RoleResponse], status_code=200)
async def reorder_roles_endpoint(
    server_id: uuid.UUID,
    reorder: RoleReorder,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = RoleService(RoleRepository())
    return await service.reorder_roles(db, server_id, user_id, reorder)


@router.delete("/servers/{server_id}/roles/{role_id}", status_code=204)
async def delete_role_endpoint(
    server_id: uuid.UUID,
    role_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = RoleService(RoleRepository())
    await service.delete_role(db, server_id, user_id, role_id)


@router.patch("/servers/{server_id}/roles/{role_id}/permissions", response_model=RoleResponse, status_code=200)
async def update_role_permissions_endpoint(
    server_id: uuid.UUID,
    role_id: uuid.UUID,
    permissions_data: RoleUpdatePermissions,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = RoleService(RoleRepository())
    return await service.update_role_permissions(
        db, server_id, user_id, role_id, permissions_data.new_permissions_bitmask
    )


@router.get(
    "/servers/{server_id}/roles/{role_id}/members",
    response_model=list[RoleMemberResponse],
)
async def get_role_members_endpoint(
    server_id: uuid.UUID,
    role_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = RoleService(RoleRepository())
    return await service.get_members_by_role(db, server_id, user_id, role_id)


@router.put("/servers/{server_id}/roles/{role_id}/members/{target_user_id}", status_code=204)
async def assign_role_endpoint(
    server_id: uuid.UUID,
    role_id: uuid.UUID,
    target_user_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = RoleService(RoleRepository())
    await service.assign_role_to_member(db, server_id, user_id, role_id, target_user_id)


@router.delete("/servers/{server_id}/roles/{role_id}/members/{target_user_id}", status_code=204)
async def remove_role_endpoint(
    server_id: uuid.UUID,
    role_id: uuid.UUID,
    target_user_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = RoleService(RoleRepository())
    await service.remove_role_from_member(db, server_id, user_id, role_id, target_user_id)


@router.patch("/servers/{server_id}/roles/{role_id}/default", response_model=RoleResponse, status_code=200)
async def set_default_role_endpoint(
    server_id: uuid.UUID,
    role_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = RoleService(RoleRepository())
    return await service.set_default_role(db, server_id, user_id, role_id)


@router.delete("/servers/{server_id}/leave", status_code=204)
async def leave_server_endpoint(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ServerService(ServerRepository())
    await service.leave_server(db, server_id, user_id)


@router.delete("/servers/{server_id}", status_code=204)
async def delete_server_endpoint(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ServerService(ServerRepository())
    await service.delete_server(db, server_id, user_id)


@router.patch("/servers/{server_id}/roles/{role_id}", response_model=RoleResponse, status_code=200)
async def update_role_endpoint(
    server_id: uuid.UUID,
    role_id: uuid.UUID,
    role_data: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = RoleService(RoleRepository())
    return await service.update_role(db, server_id, user_id, role_id, role_data)


@router.post("/servers/{server_id}/invites", response_model=InviteResponse, status_code=201)
async def create_invite_endpoint(
    server_id: uuid.UUID,
    invite_data: InviteCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = InviteService(InviteRepository())
    return await service.create_invite(db, server_id, user_id, invite_data.max_uses, invite_data.expires_in_seconds)


@router.delete("/servers/{server_id}/invites/{code}", status_code=204)
async def revoke_invite_endpoint(
    server_id: uuid.UUID,
    code: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = InviteService(InviteRepository())
    await service.revoke_invite(db, server_id, user_id, code)


@router.get("/invites/{code}", status_code=200)
async def get_invite_preview_endpoint(code: str, db: AsyncSession = Depends(get_db)):
    service = InviteService(InviteRepository())
    return await service.get_invite_preview(db, code)


@router.post("/invites/{code}/join", status_code=200)
async def join_server_via_invite_endpoint(
    code: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = InviteService(InviteRepository())
    server_id = await service.join_server(db, user_id, code)
    return {"server_id": server_id}


@router.post(
    "/servers/{server_id}/transfers",
    response_model=ServerTransferResponse,
    status_code=201,
)
async def initiate_server_transfer_endpoint(
    server_id: uuid.UUID,
    transfer_data: ServerTransferCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ServerTransferService()
    return await service.initiate_transfer(
        db, server_id=server_id, owner_id=user_id, target_user_id=transfer_data.target_user_id
    )


@router.get(
    "/servers/{server_id}/transfers/pending",
    response_model=ServerTransferResponse | None,
    status_code=200,
)
async def get_pending_transfer_endpoint(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ServerTransferService()
    return await service.get_pending_transfer(db, server_id=server_id, user_id=user_id)


@router.post(
    "/servers/{server_id}/transfers/accept",
    response_model=ServerTransferResponse,
    status_code=200,
)
async def accept_pending_transfer_endpoint(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ServerTransferService()
    return await service.accept_transfer(db, server_id=server_id, user_id=user_id)


@router.post(
    "/servers/{server_id}/transfers/reject",
    response_model=ServerTransferResponse,
    status_code=200,
)
async def reject_pending_transfer_endpoint(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ServerTransferService()
    return await service.reject_transfer(db, server_id=server_id, user_id=user_id)


@router.post(
    "/servers/{server_id}/transfers/{transfer_id}/accept",
    response_model=ServerTransferResponse,
    status_code=200,
)
async def accept_transfer_by_id_endpoint(
    server_id: uuid.UUID,
    transfer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ServerTransferService()
    return await service.accept_transfer(db, server_id=server_id, user_id=user_id, transfer_id=transfer_id)


@router.post(
    "/servers/{server_id}/transfers/{transfer_id}/reject",
    response_model=ServerTransferResponse,
    status_code=200,
)
async def reject_transfer_by_id_endpoint(
    server_id: uuid.UUID,
    transfer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ServerTransferService()
    return await service.reject_transfer(db, server_id=server_id, user_id=user_id, transfer_id=transfer_id)


@router.post(
    "/servers/{server_id}/transfers/{transfer_id}/cancel",
    response_model=ServerTransferResponse,
    status_code=200,
)
async def cancel_transfer_endpoint(
    server_id: uuid.UUID,
    transfer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ServerTransferService()
    return await service.cancel_transfer(db, server_id=server_id, user_id=user_id, transfer_id=transfer_id)


@router.get(
    "/servers/{server_id}/metrics/member-growth",
    response_model=MemberGrowthResponse,
    status_code=200,
)
@router.get(
    "/servers/{server_id}/member-growth",
    response_model=MemberGrowthResponse,
    status_code=200,
)
async def get_member_growth_endpoint(
    server_id: uuid.UUID,
    days: int | None = Query(default=None, ge=1, le=365),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ServerService(ServerRepository())
    return await service.get_member_growth(
        db=db,
        server_id=server_id,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        days=days,
    )

