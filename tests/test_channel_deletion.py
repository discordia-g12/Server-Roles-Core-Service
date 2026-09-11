import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def create_test_server(owner_id: str) -> str:
    """Helper to quickly create a server before testing channel deletion."""
    payload = {"name": "Test Server CA"}
    headers = {"x-user-id": owner_id}
    response = client.post("/api/v1/servers", data=payload, headers=headers)
    return response.json()["id"]

def create_test_channel(server_id: str, owner_id: str, name: str = "general-chat", type: str = "text") -> str:
    """Helper to create a channel inside a server."""
    payload = {"name": name, "type": type}
    headers = {"x-user-id": owner_id}
    response = client.post(f"/api/v1/servers/{server_id}/channels", json=payload, headers=headers)
    return response.json()["id"]

def test_delete_channel_success():
    """
    CA 1: Successful deletion
    Given a user with permissions confirms the deletion of a channel
    When the system processes the request
    Then the channel and its message history are permanently deleted.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    channel_id = create_test_channel(server_id, owner_id, "channel-to-delete")
    
    headers = {"x-user-id": owner_id}
    response = client.delete(f"/api/v1/servers/{server_id}/channels/{channel_id}", headers=headers)
    
    assert response.status_code == 204

def test_delete_channel_without_permissions():
    """
    CA 3: No permissions
    Given a user without administration permissions attempts to delete a channel
    When they access that option
    Then the system does not allow it.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    channel_id = create_test_channel(server_id, owner_id, "channel-to-delete")
    
    random_user_id = str(uuid.uuid4())
    headers_random = {"x-user-id": random_user_id}
    
    response = client.delete(f"/api/v1/servers/{server_id}/channels/{channel_id}", headers=headers_random)
    
    assert response.status_code == 403
    assert "detail" in response.json()

def test_delete_channel_not_found():
    """
    Attempting to delete a channel that does not exist should return 404.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    random_channel_id = str(uuid.uuid4())
    
    headers = {"x-user-id": owner_id}
    response = client.delete(f"/api/v1/servers/{server_id}/channels/{random_channel_id}", headers=headers)
    
    assert response.status_code == 404

