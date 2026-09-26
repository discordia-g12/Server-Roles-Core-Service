import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

def create_test_server(owner_id: str) -> str:
    payload = {"name": "Test Server Update Role"}
    headers = {"x-user-id": owner_id}
    response = client.post("/api/v1/servers", data=payload, headers=headers)
    return response.json()["id"]

def create_test_role(server_id: str, owner_id: str, name: str = "Moderator") -> str:
    payload = {"name": name, "color": "#ff0000"}
    headers = {"x-user-id": owner_id}
    response = client.post(f"/api/v1/servers/{server_id}/roles", json=payload, headers=headers)
    return response.json()["id"]

def get_default_role(server_id: str, owner_id: str) -> str:
    headers = {"x-user-id": owner_id}
    response = client.get(f"/api/v1/servers/{server_id}/roles", headers=headers)
    for r in response.json():
        if r["is_default"]:
            return r["id"]
    return None

def test_update_role_success():
    """CA 1: Edición exitosa"""
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Old Name")

    headers = {"x-user-id": owner_id}
    payload = {"name": "New Name", "color": "#00ff00"}
    response = client.patch(f"/api/v1/servers/{server_id}/roles/{role_id}", json=payload, headers=headers)

    assert response.status_code == 200
    assert response.json()["name"] == "New Name"
    assert response.json()["color"] == "#00ff00"

def test_update_default_role_name_fails():
    """CA 2: Rol por defecto (No se le puede cambiar el nombre)"""
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    default_role_id = get_default_role(server_id, owner_id)

    headers = {"x-user-id": owner_id}
    payload = {"name": "Hacked Name"}
    response = client.patch(f"/api/v1/servers/{server_id}/roles/{default_role_id}", json=payload, headers=headers)

    assert response.status_code == 400
    assert "Cannot change the name of the default server role" in response.json()["detail"]

@pytest.mark.parametrize("invalid_payload", [
    {"name": ""},
    {"name": "A" * 101},
    {"color": "red"},
    {"color": "#12345"},
    {"color": "#1234567"},
])
def test_update_role_invalid_data(invalid_payload):
    """CA 3: Datos inválidos (Pydantic lo frena devolviendo 422)"""
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Test Role")

    headers = {"x-user-id": owner_id}
    response = client.patch(f"/api/v1/servers/{server_id}/roles/{role_id}", json=invalid_payload, headers=headers)

    assert response.status_code == 422

def test_update_role_without_permissions():
    """CA 4: Sin permisos"""
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Admin Role")

    random_user_id = str(uuid.uuid4())
    headers = {"x-user-id": random_user_id}
    payload = {"name": "Hacked Name"}
    response = client.patch(f"/api/v1/servers/{server_id}/roles/{role_id}", json=payload, headers=headers)

    assert response.status_code == 403