import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.permissions import Permission
from app.main import app
from app.models.role import Role
from tests.conftest import TestingSessionLocal

client = TestClient(app)


def create_test_server(owner_id: str) -> str:
    """Helper to quickly create a server before testing role permission updates."""
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


def get_default_role_id(server_id: str) -> str:
    """
    The owner is auto-assigned the server's default (@everyone) role on creation
    (see ServerRepository.create_server_with_defaults), but there is no endpoint
    yet (#19) to list a server's roles. We read it straight from the DB using the
    same test session factory conftest.py wires up for the app, since this is
    setup/discovery, not the behavior under test.
    """
    async def _fetch():
        async with TestingSessionLocal() as db:
            result = await db.execute(
                select(Role).where(Role.server_id == server_id, Role.is_default.is_(True))
            )
            return str(result.scalar_one().id)

    return asyncio.run(_fetch())


def update_role_permissions(server_id: str, role_id: str, user_id: str, new_bitmask: int):
    headers = {"x-user-id": user_id}
    return client.patch(
        f"/api/v1/servers/{server_id}/roles/{role_id}/permissions",
        json={"new_permissions_bitmask": new_bitmask},
        headers=headers,
    )


def test_update_role_permissions_success():
    """
    CA 1: Edicion exitosa
    Given a user with permissions modifies the enabled permissions of an existing role
    When they confirm the changes
    Then the new permissions are applied immediately.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Moderator")

    new_bitmask = int(Permission.KICK_MEMBERS | Permission.BAN_MEMBERS)
    response = update_role_permissions(server_id, role_id, owner_id, new_bitmask)

    assert response.status_code == 200
    assert response.json()["permissions_bitmask"] == new_bitmask


def test_update_role_permissions_cannot_remove_own_administrator():
    """
    CA 2: Rol con permisos de administracion
    Given a user with permissions tries to remove the ADMINISTRATOR permission
    from their own role
    When they attempt it
    Then the system does not allow it.

    There's no "join server" / "assign role" endpoint yet (#14), so we can't
    attach a custom admin role to a non-owner user via the API. Instead we use
    the owner's own auto-assigned default (@everyone) role: first grant it
    ADMINISTRATOR (allowed today, since granting isn't restricted — see #13
    discussion), then try to remove it from that same role the owner has
    assigned to themselves.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    default_role_id = get_default_role_id(server_id)

    grant_response = update_role_permissions(
        server_id, default_role_id, owner_id, int(Permission.ADMINISTRATOR)
    )
    assert grant_response.status_code == 200
    assert grant_response.json()["permissions_bitmask"] == int(Permission.ADMINISTRATOR)

    revoke_response = update_role_permissions(
        server_id, default_role_id, owner_id, int(Permission.KICK_MEMBERS)
    )

    assert revoke_response.status_code == 403
    assert "detail" in revoke_response.json()


def test_update_role_permissions_without_permissions():
    """
    CA 3: Sin permisos
    Given a user without administration permissions tries to edit a role's permissions
    When they attempt it
    Then the system does not allow it.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Moderator")

    random_user_id = str(uuid.uuid4())
    response = update_role_permissions(
        server_id, role_id, random_user_id, int(Permission.KICK_MEMBERS)
    )

    assert response.status_code == 403
    assert "detail" in response.json()


def test_update_role_permissions_not_found():
    """
    Attempting to update permissions of a role that does not exist should return 404.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    random_role_id = str(uuid.uuid4())

    response = update_role_permissions(
        server_id, random_role_id, owner_id, int(Permission.KICK_MEMBERS)
    )

    assert response.status_code == 404


def test_update_role_permissions_role_belongs_to_another_server():
    """
    A role_id that exists but belongs to a different server should be treated
    as not found for this server — get_role_by_id filters by (server_id, role_id)
    together, so this catches a regression where that filter is dropped and a
    role could be edited through the "wrong" server_id.
    """
    owner_a = str(uuid.uuid4())
    server_a_id = create_test_server(owner_a)
    role_in_server_a = create_test_role(server_a_id, owner_a, "Role from server A")

    owner_b = str(uuid.uuid4())
    server_b_id = create_test_server(owner_b)

    response = update_role_permissions(
        server_b_id, role_in_server_a, owner_b, int(Permission.KICK_MEMBERS)
    )

    assert response.status_code == 404
