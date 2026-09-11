import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def create_test_server(owner_id: str) -> str:
    """Helper to quickly create a server before testing channel creation."""
    payload = {"name": "Test Server CA"}
    headers = {"x-user-id": owner_id}
    response = client.post("/api/v1/servers", data=payload, headers=headers)
    return response.json()["id"]

def test_create_text_channel_success():
    """
    Given a user with permissions provides a valid name and 'text' type (CA 1),
    When they attempt to create the channel,
    Then the channel is created successfully and is visible.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    
    payload = {"name": "general-chat", "type": "text"}
    headers = {"x-user-id": owner_id}
    
    response = client.post(f"/api/v1/servers/{server_id}/channels", json=payload, headers=headers)
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "general-chat"
    assert data["type"] == "text"
    assert "id" in data


def test_create_voice_channel_success():
    """
    Given a user with permissions provides a valid name and 'voice' type (CA 1),
    When they attempt to create the channel,
    Then the voice channel is created successfully.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    
    payload = {"name": "lobby", "type": "voice"}
    headers = {"x-user-id": owner_id}
    
    response = client.post(f"/api/v1/servers/{server_id}/channels", json=payload, headers=headers)
    
    assert response.status_code == 201
    assert response.json()["type"] == "voice"


def test_create_channel_fails_with_duplicate_name():
    """
    Given a user with permissions enters a name already used by another channel (CA 2),
    When they attempt to create it,
    Then the system indicates a 400 error and does not create it.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    headers = {"x-user-id": owner_id}
    payload = {"name": "announcements", "type": "text"}
    
    client.post(f"/api/v1/servers/{server_id}/channels", json=payload, headers=headers)
    
    response_duplicate = client.post(f"/api/v1/servers/{server_id}/channels", json=payload, headers=headers)
    
    assert response_duplicate.status_code == 400
    assert "detail" in response_duplicate.json()


@pytest.mark.parametrize("invalid_name", [
    "",             
    "A" * 101       
])
def test_create_channel_fails_with_invalid_name(invalid_name):
    """
    Given a user enters an empty name or an excessively long name (CA 2),
    When they attempt to create the channel,
    Then the system returns a validation error (422) and rejects it.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    headers = {"x-user-id": owner_id}
    
    payload = {"name": invalid_name, "type": "text"}
    
    response = client.post(f"/api/v1/servers/{server_id}/channels", json=payload, headers=headers)
    
    assert response.status_code == 422
    assert "detail" in response.json()


def test_create_channel_fails_with_unsupported_type():
    """
    Given a user provides an unsupported channel type like 'video' or 'streaming',
    When they attempt to create it,
    Then the system rejects it (422) since only 'text' or 'voice' are allowed.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    headers = {"x-user-id": owner_id}
    
    payload = {"name": "movies", "type": "video"}
    
    response = client.post(f"/api/v1/servers/{server_id}/channels", json=payload, headers=headers)
    
    assert response.status_code == 422
    assert "detail" in response.json()


def test_create_channel_fails_without_permissions():
    """
    Given a user without administration permissions attempts to create a channel (CA 3),
    When they access that option,
    Then the system does not allow it and returns a 403 Forbidden error.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    
    random_user_id = str(uuid.uuid4())
    headers_random = {"x-user-id": random_user_id}
    
    payload = {"name": "secret-chat", "type": "text"}
    
    response = client.post(f"/api/v1/servers/{server_id}/channels", json=payload, headers=headers_random)
    
    assert response.status_code == 403
    assert "detail" in response.json()