import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def create_test_server(owner_id: str) -> str:
    """Helper to quickly create a server before testing role creation."""
    payload = {"name": "Test Server CA"}
    headers = {"x-user-id": owner_id}
    response = client.post("/api/v1/servers", data=payload, headers=headers)
    return response.json()["id"]

def test_create_role_success():
    """
    CA 1: Successful creation
    Given a user with permissions provides a valid name for a new role
    When they confirm the creation
    Then the role is created with a default set of permissions, positioned at the end of the server's role hierarchy, and available for assignment.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    
    payload = {"name": "Moderator", "color": "#ff0000"}
    headers = {"x-user-id": owner_id}
    
    response = client.post(f"/api/v1/servers/{server_id}/roles", json=payload, headers=headers)
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Moderator"
    assert data["color"] == "#ff0000"
    assert "id" in data
    assert data["position"] == 1
    assert data["is_default"] == False
    assert data["permissions_bitmask"] > 0

def test_create_role_fails_without_permissions():
    """
    CA 2: No permissions
    Given a user without administration permissions attempts to create a role
    When they try to do so
    Then the system does not allow it.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    
    random_user_id = str(uuid.uuid4())
    headers_random = {"x-user-id": random_user_id}
    
    payload = {"name": "Admin", "color": "#000000"}
    
    response = client.post(f"/api/v1/servers/{server_id}/roles", json=payload, headers=headers_random)
    
    assert response.status_code == 403
    assert "detail" in response.json()

def test_create_role_success_without_color():
    """
    Given a user with permissions provides a valid name but no color for a new role
    When they confirm the creation
    Then the role is created successfully with color as None.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    
    payload = {"name": "Basic Role"}
    headers = {"x-user-id": owner_id}
    
    response = client.post(f"/api/v1/servers/{server_id}/roles", json=payload, headers=headers)
    
    assert response.status_code == 201
    assert response.json()["color"] is None

def test_create_role_increments_position():
    """
    Given a user with permissions creates multiple roles
    When they are created sequentially
    Then the position integer increments appropriately for each new role.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    headers = {"x-user-id": owner_id}
    
    response1 = client.post(f"/api/v1/servers/{server_id}/roles", json={"name": "Role 1"}, headers=headers)
    assert response1.status_code == 201
    assert response1.json()["position"] == 1
    
    response2 = client.post(f"/api/v1/servers/{server_id}/roles", json={"name": "Role 2"}, headers=headers)
    assert response2.status_code == 201
    assert response2.json()["position"] == 2

@pytest.mark.parametrize("invalid_color", [
    "red",          # not hex
    "#fff",         # short hex not allowed by regex ^#[0-9a-fA-F]{6}$
    "#1234567",     # too long
    "123456",       # missing #
])
def test_create_role_fails_with_invalid_color_format(invalid_color):
    """
    Given a user attempts to create a role with an invalid color format
    When they send the request
    Then the system returns a validation error.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    
    payload = {"name": "Colorful Role", "color": invalid_color}
    headers = {"x-user-id": owner_id}
    
    response = client.post(f"/api/v1/servers/{server_id}/roles", json=payload, headers=headers)
    
    assert response.status_code == 422

@pytest.mark.parametrize("invalid_name", [
    "",             
    "A" * 101       
])
def test_create_role_fails_with_invalid_name(invalid_name):
    """
    Given a user attempts to create a role with an empty or excessively long name
    When they send the request
    Then the system returns a validation error.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    headers = {"x-user-id": owner_id}
    
    payload = {"name": invalid_name}
    
    response = client.post(f"/api/v1/servers/{server_id}/roles", json=payload, headers=headers)
    
    assert response.status_code == 422

