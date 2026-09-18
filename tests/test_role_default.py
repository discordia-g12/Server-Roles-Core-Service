import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models.role import Role
from tests.conftest import TestingSessionLocal

client = TestClient(app)


def create_test_server(owner_id: str) -> str:
    """Helper to quickly create a server before testing the default role."""
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


def set_default_role(server_id: str, role_id: str, user_id: str):
    headers = {"x-user-id": user_id}
    return client.patch(f"/api/v1/servers/{server_id}/roles/{role_id}/default", headers=headers)


def delete_role(server_id: str, role_id: str, user_id: str):
    headers = {"x-user-id": user_id}
    return client.delete(f"/api/v1/servers/{server_id}/roles/{role_id}", headers=headers)


def get_everyone_role_id(server_id: str) -> str:
    """
    The owner's server is created with an auto-generated "@everyone" role,
    but there is no endpoint to list a server's roles, so this reads it
    straight from the DB, same approach used elsewhere in the test suite.
    """
    async def _fetch():
        async with TestingSessionLocal() as db:
            result = await db.execute(
                select(Role).where(Role.server_id == server_id, Role.name == "@everyone")
            )
            return str(result.scalar_one().id)

    return asyncio.run(_fetch())


def test_set_default_role_success():
    """
    CA 1: Configuracion exitosa
    Given a user with permissions selects an existing role of the server
    When they confirm the change
    Then that role becomes the one auto-assigned to new members.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Moderator")

    response = set_default_role(server_id, role_id, owner_id)

    assert response.status_code == 200
    assert response.json()["is_default"] is True


def test_set_default_role_unsets_previous_default():
    """
    Only one role can be the server's default at a time: setting a new one
    must clear the flag on whichever role held it before (the server's
    auto-created @everyone role, in this case) — proven here by the fact
    that the former default can now be deleted, which CA 2 forbids while a
    role is still the default.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Moderator")
    everyone_role_id = get_everyone_role_id(server_id)

    set_default_role(server_id, role_id, owner_id)
    response = delete_role(server_id, everyone_role_id, owner_id)

    assert response.status_code == 204


def test_set_default_role_is_idempotent():
    """Setting the already-current default role as default again should not fail."""
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Moderator")

    first = set_default_role(server_id, role_id, owner_id)
    second = set_default_role(server_id, role_id, owner_id)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["is_default"] is True


def test_cannot_delete_the_current_default_role():
    """
    CA 2: Rol por defecto no eliminable
    Given a user with permissions tries to delete the role currently set as
    default
    When they attempt it
    Then the system does not allow it until another default role is set.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Moderator")
    set_default_role(server_id, role_id, owner_id)

    response = delete_role(server_id, role_id, owner_id)

    assert response.status_code == 400
    assert "detail" in response.json()


def test_can_delete_former_default_role_after_switching():
    """
    Continuation of CA 2: once a different role is set as default, the
    previous default role is no longer protected and can be deleted.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_a = create_test_role(server_id, owner_id, "Role A")
    role_b = create_test_role(server_id, owner_id, "Role B")

    set_default_role(server_id, role_a, owner_id)
    set_default_role(server_id, role_b, owner_id)

    response = delete_role(server_id, role_a, owner_id)

    assert response.status_code == 204


def test_set_default_role_without_permissions():
    """
    CA 3: Sin permisos
    Given a user without administration permissions attempts to change the
    default role
    When they try to do so
    Then the system does not allow it.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Moderator")

    random_user_id = str(uuid.uuid4())
    response = set_default_role(server_id, role_id, random_user_id)

    assert response.status_code == 403
    assert "detail" in response.json()


def test_set_default_role_role_not_found():
    """Setting a role that does not exist as default should return 404."""
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    random_role_id = str(uuid.uuid4())

    response = set_default_role(server_id, random_role_id, owner_id)

    assert response.status_code == 404


def test_set_default_role_role_belongs_to_another_server():
    """
    A role_id that exists but belongs to a different server should be
    treated as not found for this server, same regression guard used
    across the other role endpoints.
    """
    owner_a = str(uuid.uuid4())
    server_a_id = create_test_server(owner_a)
    role_in_server_a = create_test_role(server_a_id, owner_a, "Role from server A")

    owner_b = str(uuid.uuid4())
    server_b_id = create_test_server(owner_b)

    response = set_default_role(server_b_id, role_in_server_a, owner_b)

    assert response.status_code == 404
