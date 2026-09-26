import asyncio
import uuid

from fastapi.testclient import TestClient

import tests.db_utils as db_utils
from app.main import app
from app.models.server_member import ServerMember

client = TestClient(app)


def create_test_server(owner_id: str) -> str:
    """Helper para crear un servidor rápidamente en las pruebas."""
    payload = {"name": "Test Server Leave"}
    headers = {"x-user-id": owner_id}
    response = client.post("/api/v1/servers", data=payload, headers=headers)
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def add_member_to_server(server_id: str, user_id: str) -> str:
    """
    Inserta directamente un ServerMember en la DB salteando la API (ya que 
    todavía no hay endpoint de 'join server').
    """
    async def _add():
        async with db_utils.TestingSessionLocal() as db:
            member = ServerMember(server_id=uuid.UUID(server_id), user_id=user_id)
            db.add(member)
            await db.commit()
            return str(member.id)

    return asyncio.run(_add())


def test_leave_server_success():
    """
    CA 1: Abandono exitoso
    Dado que un miembro (no owner) quiere dejar un servidor
    Cuando confirma la acción
    Entonces deja de tener acceso a los canales de ese servidor (es removido exitosamente).
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    
    member_id = str(uuid.uuid4())
    add_member_to_server(server_id, member_id)
    
    # 1. El miembro abandona el servidor exitosamente (status 204 No Content)
    headers = {"x-user-id": member_id}
    response = client.delete(f"/api/v1/servers/{server_id}/leave", headers=headers)
    
    assert response.status_code == 204
    
    # 2. Verificamos que ya no esté en la BD intentando abandonar de nuevo
    response_again = client.delete(f"/api/v1/servers/{server_id}/leave", headers=headers)
    assert response_again.status_code == 400
    assert "You are not a member of this server" in response_again.json()["detail"]


def test_leave_server_owner_fails():
    """
    CA 2: Owner no puede abandonar directamente
    Dado que el owner de un servidor intenta abandonarlo
    Cuando confirma la acción
    Entonces el sistema le exige transferir la propiedad o eliminar el servidor antes de poder salir.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    
    headers = {"x-user-id": owner_id}
    response = client.delete(f"/api/v1/servers/{server_id}/leave", headers=headers)
    
    assert response.status_code == 400
    assert "Owners cannot leave their own server directly" in response.json()["detail"]


def test_leave_server_not_a_member_fails():
    """
    Dado que un usuario que NO es miembro intenta abandonar
    Entonces el sistema retorna error indicando que no pertenece al servidor.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    
    random_user_id = str(uuid.uuid4())
    headers = {"x-user-id": random_user_id}
    response = client.delete(f"/api/v1/servers/{server_id}/leave", headers=headers)
    
    assert response.status_code == 400
    assert "You are not a member of this server" in response.json()["detail"]


def test_leave_server_not_found():
    """
    Dado que se intenta abandonar un servidor que no existe (404 Not Found)
    """
    random_server_id = str(uuid.uuid4())
    random_user_id = str(uuid.uuid4())
    headers = {"x-user-id": random_user_id}
    
    response = client.delete(f"/api/v1/servers/{random_server_id}/leave", headers=headers)
    
    assert response.status_code == 404