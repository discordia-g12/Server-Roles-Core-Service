import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories.server import ServerRepository
from app.schemas.server import ServerCreate, ServerResponse
from app.services.server import ServerService

router = APIRouter(prefix="/api/v1", tags=["servers"])


@router.post("/servers", response_model=ServerResponse, status_code=201)
async def create_server_endpoint(
    name: str = Form(..., min_length=1, max_length=100, pattern=r"^[^\x00]+$"),
    icon: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    # owner_id: uuid.UUID = Depends(get_current_user_id),  # TODO: conectar con auth
):
    owner_id = uuid.uuid4()  # mock hasta que esté el login

    server_data = ServerCreate(name=name)
    service = ServerService(ServerRepository())
    created_server = await service.create_server(
        db, owner_id=owner_id, server_name=server_data.name, icon=icon
    )
    return created_server