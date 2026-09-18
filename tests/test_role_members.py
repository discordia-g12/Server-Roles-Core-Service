import asyncio
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.models.role_assignment import RoleAssignment
from app.models.server_member import ServerMember
from tests.conftest import TestingSessionLocal

client = TestClient(app)


def create_test_server(owner_id: str) -> str:
    """Helper to quickly create a server before testing role member listing."""
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


def assign_role_to_user(server_id: str, role_id: str, user_id: str, nickname: str | None = None) -> str:
    """
    Directly inserts a ServerMember + RoleAssignment row to simulate a member
    having a role. There is no "join server" / "assign role" endpoint yet
    (#14), so this bypasses the API for setup only, same approach already
    used in tests/test_role_update_permissions.py.
    """

    async def _assign():
        async with TestingSessionLocal() as db:
            member = ServerMember(server_id=uuid.UUID(server_id), user_id=user_id, nickname=nickname)
            db.add(member)
            await db.flush()
            assignment = RoleAssignment(server_member_id=member.id, role_id=uuid.UUID(role_id))
            db.add(assignment)
            await db.commit()
            return str(member.id)

    return asyncio.run(_assign())


def get_role_members(server_id: str, role_id: str, user_id: str):
    headers = {"x-user-id": user_id}
    return client.get(f"/api/v1/servers/{server_id}/roles/{role_id}/members", headers=headers)


def test_get_role_members_success():
    """
    CA 1: Listado exitoso
    Given a user with permissions selects an existing role
    When they query its members
    Then the system shows the list of all members that have that role assigned.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Moderator")

    member_a = str(uuid.uuid4())
    member_b = str(uuid.uuid4())
    assign_role_to_user(server_id, role_id, member_a, nickname="Alice")
    assign_role_to_user(server_id, role_id, member_b, nickname="Bob")

    response = get_role_members(server_id, role_id, owner_id)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert {m["user_id"] for m in body} == {member_a, member_b}
    assert {m["nickname"] for m in body} == {"Alice", "Bob"}


def test_get_role_members_empty_role():
    """
    A role that exists but has no members assigned should return an empty list,
    not an error.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Empty Role")

    response = get_role_members(server_id, role_id, owner_id)

    assert response.status_code == 200
    assert response.json() == []


def test_get_role_members_only_returns_members_with_that_role():
    """
    Regression guard: a member assigned to a different role in the same
    server must not show up when querying another role's members.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_a = create_test_role(server_id, owner_id, "Role A")
    role_b = create_test_role(server_id, owner_id, "Role B")

    member_a = str(uuid.uuid4())
    member_b = str(uuid.uuid4())
    assign_role_to_user(server_id, role_a, member_a)
    assign_role_to_user(server_id, role_b, member_b)

    response = get_role_members(server_id, role_a, owner_id)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["user_id"] == member_a


def test_get_role_members_without_permissions():
    """
    CA implicit (consistent with the other role endpoints): a user without
    administration permissions cannot list a role's members.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Moderator")

    random_user_id = str(uuid.uuid4())
    response = get_role_members(server_id, role_id, random_user_id)

    assert response.status_code == 403
    assert "detail" in response.json()


def test_get_role_members_role_not_found():
    """
    Querying members of a role that does not exist should return 404.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    random_role_id = str(uuid.uuid4())

    response = get_role_members(server_id, random_role_id, owner_id)

    assert response.status_code == 404


def test_get_role_members_role_belongs_to_another_server():
    """
    A role_id that exists but belongs to a different server should be
    treated as not found for this server, same regression guard used in
    tests/test_role_update_permissions.py.
    """
    owner_a = str(uuid.uuid4())
    server_a_id = create_test_server(owner_a)
    role_in_server_a = create_test_role(server_a_id, owner_a, "Role from server A")

    owner_b = str(uuid.uuid4())
    server_b_id = create_test_server(owner_b)

    response = get_role_members(server_b_id, role_in_server_a, owner_b)

    assert response.status_code == 404
