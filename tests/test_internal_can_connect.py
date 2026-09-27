import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

def create_test_server(owner_id: str) -> str:
    payload = {"name": "Test Server Internal Voice"}
    headers = {"x-user-id": owner_id}
    response = client.post("/api/v1/servers", data=payload, headers=headers)
    assert response.status_code == 201, response.json()
    return response.json()["id"]

def create_test_voice_channel(server_id: str, owner_id: str) -> str:
    payload = {"name": "test-voice-channel", "type": "voice"}
    headers = {"x-user-id": owner_id}
    response = client.post(f"/api/v1/servers/{server_id}/channels", json=payload, headers=headers)
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def test_can_connect_success():
    """
    Si el usuario tiene permisos (el owner siempre tiene permisos base), 
    devuelve 200 OK y can_connect en True.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    channel_id = create_test_voice_channel(server_id, owner_id)
    
    response = client.get(f"/internal/channels/{channel_id}/can-connect?user_id={owner_id}")
    
    assert response.status_code == 200
    assert response.json() == {"can_connect": True}


def test_can_connect_channel_not_found():
    """
    Si el canal no existe en la base de datos, devuelve HTTP 404 Not Found.
    """
    owner_id = str(uuid.uuid4())
    fake_channel_id = str(uuid.uuid4())
    
    response = client.get(f"/internal/channels/{fake_channel_id}/can-connect?user_id={owner_id}")
    
    assert response.status_code == 404
    assert response.json()["detail"] == "Channel not found"


def test_can_connect_user_not_member():
    """
    Si un usuario no pertenece al servidor del canal, 
    se le deniega el acceso con HTTP 403 Forbidden.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    channel_id = create_test_voice_channel(server_id, owner_id)
    
    random_user_id = str(uuid.uuid4())
    
    response = client.get(f"/internal/channels/{channel_id}/can-connect?user_id={random_user_id}")
    
    assert response.status_code == 403
    assert "User is not a member" in response.json()["detail"]