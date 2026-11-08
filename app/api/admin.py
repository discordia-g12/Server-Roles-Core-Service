import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_staff
from app.db.session import get_db
from app.schemas.admin import AdminServerResponse, SuspendServerRequest
from app.services.server_suspension import ServerSuspensionService

# Backoffice (solo staff). Kong exige validate("staff") en /api/v1/admin/servers y acá se vuelve a chequear el
# rol (Gateway ADR-002, reglas 1 y 2). No pasa por reject_suspended_server: el staff gestiona servidores
# suspendidos.
router = APIRouter(prefix="/api/v1/admin/servers", tags=["backoffice: servers"])
service = ServerSuspensionService()


@router.get("/suspended", response_model=list[AdminServerResponse], status_code=status.HTTP_200_OK)
async def list_suspended_servers(
    db: AsyncSession = Depends(get_db),
    _staff: str = Depends(require_staff),
):
    """Servidores suspendidos, el más reciente primero."""
    return await service.list_suspended(db)


@router.post("/{server_id}/suspension", response_model=AdminServerResponse, status_code=status.HTTP_201_CREATED)
async def suspend_server(
    server_id: uuid.UUID,
    payload: SuspendServerRequest,
    db: AsyncSession = Depends(get_db),
    staff_user_id: str = Depends(require_staff),
):
    """Suspende el servidor (por id: el nombre no es único). Nadie puede usarlo hasta que se levante; su contenido
    se conserva. 404 si no existe, 409 si ya estaba suspendido."""
    return await service.suspend(db, server_id, payload.reason, staff_user_id)


@router.delete("/{server_id}/suspension", response_model=AdminServerResponse, status_code=status.HTTP_200_OK)
async def lift_server_suspension(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    staff_user_id: str = Depends(require_staff),
):
    """Levanta la suspensión: los miembros recuperan el acceso normal. 404 si no existe, 409 si no estaba
    suspendido."""
    return await service.lift(db, server_id, staff_user_id)
