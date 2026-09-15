import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def create_test_server(owner_id: str) -> str:
    payload = {"name": "Test Server Internal"}
    headers = {"x-user-id": owner_id}
    response = client.post("/api/v1/servers", data=payload, headers=headers)
    assert response.status_code == 201, response.json()
    return response.json()["id"]

def create_test_channel(server_id: str, owner_id: str) -> str:
    payload = {"name": "test-channel", "type": "text"}
    headers = {"x-user-id": owner_id}
    response = client.post(f"/api/v1/servers/{server_id}/channels", json=payload, headers=headers)
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def test_can_send_success():
    """
    CA 4: Aprobación (200)
    Si el usuario tiene permisos (el owner siempre tiene permisos base en tu ADR), devuelve 200 OK.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    channel_id = create_test_channel(server_id, owner_id)
    
    response = client.get(f"/internal/channels/{channel_id}/can-send?user_id={owner_id}")
    
    assert response.status_code == 200
    assert response.json() == {"can_send": True}


def test_can_send_channel_not_found():
    """
    CA 2: Validar Existencia (404)
    Si el canal no existe en la base de datos, devuelve HTTP 404 Not Found.
    """
    owner_id = str(uuid.uuid4())
    fake_channel_id = str(uuid.uuid4())
    
    response = client.get(f"/internal/channels/{fake_channel_id}/can-send?user_id={owner_id}")
    
    assert response.status_code == 404
    assert response.json()["detail"] == "Channel not found"


def test_can_send_user_not_member():
    """
    CA 3: Validar Permisos (403)
    Si un usuario no pertenece al servidor del canal, se le deniega el acceso con HTTP 403 Forbidden.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    channel_id = create_test_channel(server_id, owner_id)
    
    random_user_id = str(uuid.uuid4())
    
    response = client.get(f"/internal/channels/{channel_id}/can-send?user_id={random_user_id}")
    
    assert response.status_code == 403
    assert "User is not a member" in response.json()["detail"]