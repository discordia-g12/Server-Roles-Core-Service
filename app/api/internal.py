import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories.server import ServerRepository
from app.schemas.internal import (
    CanConnectResponse,
    CanSendResponse,
    ChannelAccessResponse,
    ServerActivityMetricsInternalResponse,
    ServerMemberIdsResponse,
    ServerPermissionsResponse,
    ServersCreatedMetricsResponse,
    VisibleChannelsResponse,
)
from app.services.channel_access import ChannelAccessService
from app.services.server import ServerService

# Endpoints que consultan Chat, Voice y Notification-Audit-Metrics (nodo realtime) por el puerto 8002.
# No pasan por Kong.
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


@router.get("/servers/{server_id}/member-ids", response_model=ServerMemberIdsResponse, status_code=200)
async def server_member_ids(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Chat: a quién avisarle por el inbox que cambió la configuración del servidor (server.updated).
    404 si el servidor no existe."""
    user_ids = await ServerService(ServerRepository()).get_member_user_ids(db, server_id)
    return {"server_id": str(server_id), "user_ids": user_ids}


@router.get(
    "/servers/{server_id}/members/{user_id}/permissions",
    response_model=ServerPermissionsResponse,
    status_code=200,
)
async def server_member_permissions(
    server_id: uuid.UUID,
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Notification-Audit-Metrics: verificar si un usuario tiene permisos de moderación en el servidor."""
    return await ChannelAccessService().get_server_permissions(db, server_id, user_id)


@router.get("/metrics/servers", response_model=ServersCreatedMetricsResponse, status_code=200)
async def servers_created_metrics(
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
    db: AsyncSession = Depends(get_db),
):
    """Notification-Audit-Metrics: servidores creados en [from, to) para las métricas globales del backoffice.
    Fechas ISO 8601 (sin zona se toman como UTC). 400 si from >= to; 422 si no son fechas."""
    return await ServerService(ServerRepository()).get_servers_created_metrics(db, from_, to)


@router.get("/metrics/servers/{server_id}", response_model=ServerActivityMetricsInternalResponse, status_code=200)
async def server_activity_metrics(
    server_id: uuid.UUID,
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
    db: AsyncSession = Depends(get_db),
):
    """Notification-Audit-Metrics: canales y nuevos miembros de un servidor en [from, to)."""
    return await ServerService(ServerRepository()).get_server_activity_metrics(db, server_id, from_, to)
