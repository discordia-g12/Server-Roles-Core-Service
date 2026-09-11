import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def create_test_server(owner_id: str) -> str:
    """Helper to quickly create a server before testing role deletion."""
    payload = {"name": "Test Server CA"}
    headers = {"x-user-id": owner_id}
    response = client.post("/api/v1/servers", data=payload, headers=headers)
    return response.json()["id"]

def create_test_role(server_id: str, owner_id: str, name: str = "Moderator") -> str:
    """Helper to create a role inside a server."""
    payload = {"name": name}
    headers = {"x-user-id": owner_id}
    response = client.post(f"/api/v1/servers/{server_id}/roles", json=payload, headers=headers)
    return response.json()["id"]

def test_delete_role_success():
    """
    CA 1: Successful deletion
    Given a user with permissions confirms the deletion of a role
    When the action is executed
    Then the role is deleted and members who had it lose those permissions.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Role to delete")
    
    headers = {"x-user-id": owner_id}
    response = client.delete(f"/api/v1/servers/{server_id}/roles/{role_id}", headers=headers)
    
    assert response.status_code == 204

def test_delete_role_without_permissions():
    """
    CA 2: No permissions
    Given a user without administration permissions attempts to delete a role
    When they try to do so
    Then the system does not allow it.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Role to delete")
    
    random_user_id = str(uuid.uuid4())
    headers_random = {"x-user-id": random_user_id}
    
    response = client.delete(f"/api/v1/servers/{server_id}/roles/{role_id}", headers=headers_random)
    
    assert response.status_code == 403
    assert "detail" in response.json()

def test_delete_role_not_found():
    """
    Attempting to delete a role that does not exist should return 404.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    random_role_id = str(uuid.uuid4())
    
    headers = {"x-user-id": owner_id}
    response = client.delete(f"/api/v1/servers/{server_id}/roles/{random_role_id}", headers=headers)
    
    assert response.status_code == 404
