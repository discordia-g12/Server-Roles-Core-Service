import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

def create_test_server(owner_id: str) -> str:
    """Helper to quickly create a server before testing channel updates."""
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

def test_update_channel_success():
    """
    CA 1: Successful edit
    Given a user with permissions edits the name or topic of a channel with valid data
    When they save the changes
    Then they are persisted and reflected for all members.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    channel_id = create_test_channel(server_id, owner_id, "old-name")
    
    headers = {"x-user-id": owner_id}
    payload = {"name": "new-name", "topic": "New discussion topic"}
    
    response = client.patch(f"/api/v1/servers/{server_id}/channels/{channel_id}", json=payload, headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "new-name"
    assert data["topic"] == "New discussion topic"

def test_update_channel_without_permissions():
    """
    CA 2: No permissions
    Given a user without administration permissions attempts to edit a channel
    When they access that option
    Then the system does not allow it.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    channel_id = create_test_channel(server_id, owner_id, "chat")
    
    random_user_id = str(uuid.uuid4())
    headers_random = {"x-user-id": random_user_id}
    payload = {"name": "hacked-name"}
    
    response = client.patch(f"/api/v1/servers/{server_id}/channels/{channel_id}", json=payload, headers=headers_random)
    
    assert response.status_code == 403
    assert "detail" in response.json()

def test_update_channel_fails_with_duplicate_name():
    """
    Editing a channel to a name that already exists in the same category should fail.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    create_test_channel(server_id, owner_id, "existing-channel")
    channel_id = create_test_channel(server_id, owner_id, "my-channel")
    
    headers = {"x-user-id": owner_id}
    payload = {"name": "existing-channel"}
    
    response = client.patch(f"/api/v1/servers/{server_id}/channels/{channel_id}", json=payload, headers=headers)
    
    assert response.status_code == 400

def test_update_channel_not_found():
    """
    Attempting to edit a channel that does not exist should return 404.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    random_channel_id = str(uuid.uuid4())
    
    headers = {"x-user-id": owner_id}
    payload = {"name": "new-name"}
    
    response = client.patch(f"/api/v1/servers/{server_id}/channels/{random_channel_id}", json=payload, headers=headers)
    
    assert response.status_code == 404

