import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def create_test_server(owner_id: str) -> str:
    """Helper to quickly create a server before testing role listing."""
    payload = {"name": "Test Server"}
    headers = {"x-user-id": owner_id}
    response = client.post("/api/v1/servers", data=payload, headers=headers)
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def create_test_role(server_id: str, owner_id: str, name: str = "Moderator") -> str:
    """Helper to create a role inside a server."""
    payload = {"name": name}
    headers = {"x-user-id": owner_id}
    response = client.post(f"/api/v1/servers/{server_id}/roles", json=payload, headers=headers)
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def get_roles(server_id: str, user_id: str):
    headers = {"x-user-id": user_id}
    return client.get(f"/api/v1/servers/{server_id}/roles", headers=headers)


def test_get_roles_success_includes_default_role():
    """
    CA 1: Listado exitoso
    Given a user with permissions consults a server's roles
    When they access it
    Then they see every role of the server, in position order.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)

    response = get_roles(server_id, owner_id)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "@everyone"
    assert body[0]["is_default"] is True


def test_get_roles_ordered_by_position():
    """
    Roles must come back ordered by position (creation order), matching the
    order a client would use to render a role hierarchy.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    create_test_role(server_id, owner_id, "Moderator")
    create_test_role(server_id, owner_id, "VIP")

    response = get_roles(server_id, owner_id)

    assert response.status_code == 200
    body = response.json()
    names = [r["name"] for r in body]
    assert names == ["@everyone", "Moderator", "VIP"]
    positions = [r["position"] for r in body]
    assert positions == sorted(positions)


def test_get_roles_without_permissions():
    """
    CA 2: Sin permisos
    Given a user without administration permissions attempts to list a
    server's roles
    When they try to do so
    Then the system does not allow it.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)

    random_user_id = str(uuid.uuid4())
    response = get_roles(server_id, random_user_id)

    assert response.status_code == 403
    assert "detail" in response.json()


def test_get_roles_only_returns_roles_from_that_server():
    """
    Regression guard: roles from a different server must not leak into this
    server's role listing.
    """
    owner_a = str(uuid.uuid4())
    server_a_id = create_test_server(owner_a)
    create_test_role(server_a_id, owner_a, "Role from server A")

    owner_b = str(uuid.uuid4())
    server_b_id = create_test_server(owner_b)
    create_test_role(server_b_id, owner_b, "Role from server B")

    response = get_roles(server_b_id, owner_b)

    assert response.status_code == 200
    body = response.json()
    names = [r["name"] for r in body]
    assert "Role from server A" not in names
    assert "Role from server B" in names
