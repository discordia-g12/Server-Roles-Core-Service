import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.internal import (
    CanConnectResponse,
    CanSendResponse,
    ChannelAccessResponse,
    VisibleChannelsResponse,
)
from app.services.channel_access import ChannelAccessService

# Endpoints que consultan Chat y Voice (nodo realtime) por el puerto 8002. No pasan por Kong.
router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/channels/{channel_id}/access", response_model=ChannelAccessResponse, status_code=200)
async def channel_access(
    channel_id: uuid.UUID,
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Chat: abrir el WebSocket y leer el historial. 404 canal inexistente; 403 no miembro, baneado o sin
    VIEW_CHANNELS; 200 con `can_send`, `muted_until`, `can_mention_everyone` y `mentionable_role_ids`."""
    return await ChannelAccessService().get_text_channel_access(db, channel_id, user_id)


@router.get("/users/{user_id}/visible-channels", response_model=VisibleChannelsResponse, status_code=200)
async def visible_channels(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Chat: los canales de texto que el usuario puede ver y sus roles, para calcular no leídos y menciones.
    200 con listas vacías si no es miembro de ningún servidor."""
    return await ChannelAccessService().get_visible_text_channels(db, user_id)


@router.get("/channels/{channel_id}/can-send", response_model=CanSendResponse, status_code=200)
async def can_send_message(
    channel_id: uuid.UUID,
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Deprecado: Chat usa /access. Se borra cuando no quede ninguna versión de Chat que lo llame."""
    return await ChannelAccessService().check_can_send(db, channel_id, user_id)


@router.get("/channels/{channel_id}/can-connect", response_model=CanConnectResponse, status_code=200)
async def can_connect(
    channel_id: uuid.UUID,
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Voice: unirse a un canal de voz (CONNECT)."""
    return await ChannelAccessService().check_can_connect(db, channel_id, user_id)
