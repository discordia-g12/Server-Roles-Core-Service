import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.channel import ChannelCreate, ChannelResponse
from app.repositories.channel import ChannelRepository
from app.services.channel import ChannelService
from app.db.session import get_db
from app.repositories.server import ServerRepository
from app.schemas.server import ServerCreate, ServerResponse
from app.services.server import ServerService

router = APIRouter(prefix="/api/v1", tags=["servers"])


# MOCK DE AUTH: Función que luego se reemplazará por la validación del Token JWT
# NO OLVIDARSE DE CAMBIAR ESTO!!!
async def get_current_user_id(
    x_user_id: uuid.UUID = Header(..., description="User ID (Mocks Auth)")
) -> uuid.UUID:
    return x_user_id

@router.post("/servers", response_model=ServerResponse, status_code=201)
async def create_server_endpoint(
    name: str = Form(..., min_length=1, max_length=100, pattern=r"^[^\x00]+$"),
    icon: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    owner_id: uuid.UUID = Depends(get_current_user_id) 
):
    server_data = ServerCreate(name=name)
    service = ServerService(ServerRepository())
    
    created_server = await service.create_server(
        db, owner_id=owner_id, server_name=server_data.name, icon=icon
    )
    return created_server




@router.post("/servers/{server_id}/channels", response_model=ChannelResponse, status_code=201)
async def create_channel_endpoint(
    server_id: uuid.UUID,
    channel_data: ChannelCreate,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id), 
):
    service = ChannelService(ChannelRepository())
    return await service.create_channel(db, server_id, user_id, channel_data)

@router.delete("/servers/{server_id}/channels/{channel_id}", status_code=204)
async def delete_channel_endpoint(
    server_id: uuid.UUID,
    channel_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    service = ChannelService(ChannelRepository())
    await service.delete_channel(db, server_id, user_id, channel_id)
