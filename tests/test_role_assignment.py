import asyncio
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.models.server_member import ServerMember
from tests import db_utils

client = TestClient(app)


def create_test_server(owner_id: str) -> str:
    """Helper to quickly create a server before testing role assignment."""
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


def create_test_member(server_id: str, user_id: str, nickname: str | None = None) -> str:
    """
    Directly inserts a ServerMember row (no role assigned) to simulate a user
    that already joined the server. There is no "join server" endpoint yet
    (#4), so this bypasses the API for setup only, same approach already used
    in tests/test_role_members.py.
    """

    async def _create():
        async with db_utils.TestingSessionLocal() as db:
            member = ServerMember(server_id=uuid.UUID(server_id), user_id=user_id, nickname=nickname)
            db.add(member)
            await db.commit()
            return str(member.id)

    return asyncio.run(_create())


def assign_role(server_id: str, role_id: str, user_id: str, target_user_id: str):
    headers = {"x-user-id": user_id}
    return client.put(
        f"/api/v1/servers/{server_id}/roles/{role_id}/members/{target_user_id}", headers=headers
    )


def remove_role(server_id: str, role_id: str, user_id: str, target_user_id: str):
    headers = {"x-user-id": user_id}
    return client.delete(
        f"/api/v1/servers/{server_id}/roles/{role_id}/members/{target_user_id}", headers=headers
    )


def get_role_members(server_id: str, role_id: str, user_id: str):
    headers = {"x-user-id": user_id}
    return client.get(f"/api/v1/servers/{server_id}/roles/{role_id}/members", headers=headers)


def test_assign_role_success():
    """
    CA 1: Asignacion exitosa
    Given a user with permissions selects a role and a server member
    When they confirm the assignment
    Then the member ends up with that role and its associated permissions.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Moderator")

    target_user_id = str(uuid.uuid4())
    create_test_member(server_id, target_user_id, nickname="Alice")

    response = assign_role(server_id, role_id, owner_id, target_user_id)
    assert response.status_code == 204

    members = get_role_members(server_id, role_id, owner_id).json()
    assert {m["user_id"] for m in members} == {target_user_id}


def test_assign_role_is_idempotent():
    """
    Assigning the same role twice must not fail nor duplicate the member
    in the role's member list.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Moderator")

    target_user_id = str(uuid.uuid4())
    create_test_member(server_id, target_user_id)

    first = assign_role(server_id, role_id, owner_id, target_user_id)
    second = assign_role(server_id, role_id, owner_id, target_user_id)

    assert first.status_code == 204
    assert second.status_code == 204
    members = get_role_members(server_id, role_id, owner_id).json()
    assert len(members) == 1


def test_assign_role_without_permissions():
    """
    CA 3: Sin permisos
    Given a user without administration permissions attempts to assign a role
    When they try to do so
    Then the system does not allow it.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Moderator")

    target_user_id = str(uuid.uuid4())
    create_test_member(server_id, target_user_id)

    random_user_id = str(uuid.uuid4())
    response = assign_role(server_id, role_id, random_user_id, target_user_id)

    assert response.status_code == 403
    assert "detail" in response.json()


def test_assign_role_role_not_found():
    """Assigning a role that does not exist should return 404."""
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)

    target_user_id = str(uuid.uuid4())
    create_test_member(server_id, target_user_id)

    random_role_id = str(uuid.uuid4())
    response = assign_role(server_id, random_role_id, owner_id, target_user_id)

    assert response.status_code == 404


def test_assign_role_member_not_found():
    """
    Assigning a role to a user who never joined the server (no ServerMember
    row) should return 404.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Moderator")

    never_joined_user_id = str(uuid.uuid4())
    response = assign_role(server_id, role_id, owner_id, never_joined_user_id)

    assert response.status_code == 404


def test_remove_role_success():
    """
    CA 2: Quitar rol
    Given a member has a role assigned
    When a user with permissions removes it
    Then the member no longer has the permissions associated with that role.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Moderator")

    target_user_id = str(uuid.uuid4())
    create_test_member(server_id, target_user_id)
    assign_role(server_id, role_id, owner_id, target_user_id)

    response = remove_role(server_id, role_id, owner_id, target_user_id)
    assert response.status_code == 204

    members = get_role_members(server_id, role_id, owner_id).json()
    assert members == []


def test_remove_role_not_assigned():
    """
    Removing a role from a member that does not currently have it assigned
    should return 404.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Moderator")

    target_user_id = str(uuid.uuid4())
    create_test_member(server_id, target_user_id)

    response = remove_role(server_id, role_id, owner_id, target_user_id)

    assert response.status_code == 404


def test_remove_role_without_permissions():
    """A user without administration permissions cannot remove a role."""
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Moderator")

    target_user_id = str(uuid.uuid4())
    create_test_member(server_id, target_user_id)
    assign_role(server_id, role_id, owner_id, target_user_id)

    random_user_id = str(uuid.uuid4())
    response = remove_role(server_id, role_id, random_user_id, target_user_id)

    assert response.status_code == 403
    assert "detail" in response.json()


def test_remove_role_role_not_found():
    """Removing a role that does not exist should return 404."""
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)

    target_user_id = str(uuid.uuid4())
    create_test_member(server_id, target_user_id)

    random_role_id = str(uuid.uuid4())
    response = remove_role(server_id, random_role_id, owner_id, target_user_id)

    assert response.status_code == 404


def test_remove_role_member_not_found():
    """
    Removing a role from a user who never joined the server (no ServerMember
    row) should return 404.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_id = create_test_role(server_id, owner_id, "Moderator")

    never_joined_user_id = str(uuid.uuid4())
    response = remove_role(server_id, role_id, owner_id, never_joined_user_id)

    assert response.status_code == 404


def test_assign_role_role_belongs_to_another_server():
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
    target_user_id = str(uuid.uuid4())
    create_test_member(server_b_id, target_user_id)

    response = assign_role(server_b_id, role_in_server_a, owner_b, target_user_id)

    assert response.status_code == 404


def test_assign_role_member_belongs_to_another_server():
    """
    A target user who is a member of a different server (not this one)
    should be treated as not found, same isolation guarantee that
    get_member_by_user_id gives by filtering on server_id.
    """
    owner_a = str(uuid.uuid4())
    server_a_id = create_test_server(owner_a)

    owner_b = str(uuid.uuid4())
    server_b_id = create_test_server(owner_b)
    role_in_server_b = create_test_role(server_b_id, owner_b, "Moderator")

    member_of_server_a = str(uuid.uuid4())
    create_test_member(server_a_id, member_of_server_a)

    response = assign_role(server_b_id, role_in_server_b, owner_b, member_of_server_a)

    assert response.status_code == 404


def test_remove_role_role_belongs_to_another_server():
    """
    Same cross-server isolation guard as
    test_assign_role_role_belongs_to_another_server, for the remove endpoint.
    """
    owner_a = str(uuid.uuid4())
    server_a_id = create_test_server(owner_a)
    role_in_server_a = create_test_role(server_a_id, owner_a, "Role from server A")

    owner_b = str(uuid.uuid4())
    server_b_id = create_test_server(owner_b)
    target_user_id = str(uuid.uuid4())
    create_test_member(server_b_id, target_user_id)

    response = remove_role(server_b_id, role_in_server_a, owner_b, target_user_id)

    assert response.status_code == 404


def test_remove_role_member_belongs_to_another_server():
    """
    Same cross-server isolation guard as
    test_assign_role_member_belongs_to_another_server, for the remove endpoint.
    """
    owner_a = str(uuid.uuid4())
    server_a_id = create_test_server(owner_a)

    owner_b = str(uuid.uuid4())
    server_b_id = create_test_server(owner_b)
    role_in_server_b = create_test_role(server_b_id, owner_b, "Moderator")

    member_of_server_a = str(uuid.uuid4())
    create_test_member(server_a_id, member_of_server_a)

    response = remove_role(server_b_id, role_in_server_b, owner_b, member_of_server_a)

    assert response.status_code == 404
