import asyncio
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.models.server_member import ServerMember
from tests import db_utils

client = TestClient(app)


def create_test_server(owner_id: str) -> str:
    """Helper to quickly create a server before testing the member listing."""
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


def get_default_role_id(server_id: str, owner_id: str) -> str:
    headers = {"x-user-id": owner_id}
    roles = client.get(f"/api/v1/servers/{server_id}/roles", headers=headers).json()
    return next(role["id"] for role in roles if role["is_default"])


def create_test_members(server_id: str, count: int) -> list[str]:
    """
    Directly inserts ServerMember rows (no role assigned) to simulate users
    that already joined the server. There is no "join server" endpoint yet,
    so this bypasses the API for setup only, same approach as
    tests/test_role_assignment.py.
    """

    async def _create():
        user_ids = [str(uuid.uuid4()) for _ in range(count)]
        async with db_utils.TestingSessionLocal() as db:
            for user_id in user_ids:
                db.add(ServerMember(server_id=uuid.UUID(server_id), user_id=user_id))
            await db.commit()
        return user_ids

    return asyncio.run(_create())


def get_members(server_id: str, user_id: str, **params):
    headers = {"x-user-id": user_id}
    return client.get(f"/api/v1/servers/{server_id}/members", headers=headers, params=params)


def test_get_members_success_includes_owner_with_default_role():
    """
    CA 1: Successful listing
    Given a user that belongs to a server requests its members
    When the server processes the request
    Then they get the members with user id, nickname and assigned roles.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    default_role_id = get_default_role_id(server_id, owner_id)

    response = get_members(server_id, owner_id)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    member = body["items"][0]
    assert member["user_id"] == owner_id
    assert member["nickname"] is None
    assert member["role_ids"] == [default_role_id]
    assert "joined_at" not in member


def test_get_members_includes_every_assigned_role():
    """A member with several roles must list all of them in role_ids."""
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    default_role_id = get_default_role_id(server_id, owner_id)
    moderator_id = create_test_role(server_id, owner_id, "Moderator")
    headers = {"x-user-id": owner_id}
    assign = client.put(f"/api/v1/servers/{server_id}/roles/{moderator_id}/members/{owner_id}", headers=headers)
    assert assign.status_code == 204

    response = get_members(server_id, owner_id)

    assert response.status_code == 200
    role_ids = response.json()["items"][0]["role_ids"]
    assert sorted(role_ids) == sorted([default_role_id, moderator_id])


def test_get_members_member_without_roles_has_empty_role_ids():
    """A member with no role assigned must come back with an empty role_ids list."""
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    create_test_members(server_id, 1)

    response = get_members(server_id, owner_id, limit=100)

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    assert [] in [item["role_ids"] for item in items]


def test_get_members_is_paginated_by_default():
    """
    CA 2: Large list
    Given a server with many members
    When the user opens the member list without specifying a page size
    Then they get a first page (50 by default) plus the total, and can ask
    for the following ones with an offset.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    create_test_members(server_id, 54)

    first_page = get_members(server_id, owner_id).json()
    second_page = get_members(server_id, owner_id, offset=50).json()

    assert first_page["total"] == 55
    assert first_page["limit"] == 50
    assert first_page["offset"] == 0
    assert len(first_page["items"]) == 50
    assert second_page["offset"] == 50
    assert len(second_page["items"]) == 5

    all_ids = [m["id"] for m in first_page["items"] + second_page["items"]]
    assert len(set(all_ids)) == 55


def test_get_members_respects_custom_limit():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    create_test_members(server_id, 4)

    body = get_members(server_id, owner_id, limit=2).json()

    assert body["total"] == 5
    assert body["limit"] == 2
    assert len(body["items"]) == 2


def test_get_members_rejects_invalid_pagination_params():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)

    assert get_members(server_id, owner_id, limit=0).status_code == 422
    assert get_members(server_id, owner_id, limit=101).status_code == 422
    assert get_members(server_id, owner_id, offset=-1).status_code == 422


def test_get_members_any_member_can_list():
    """Listing members is not restricted to role managers, any member can see it."""
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    (regular_user_id,) = create_test_members(server_id, 1)

    response = get_members(server_id, regular_user_id)

    assert response.status_code == 200
    assert response.json()["total"] == 2


def test_get_members_user_not_in_server():
    """
    CA 3: User that does not belong to the server
    Given a user that is not a member of the server tries to see its members
    When they try to do so
    Then the system does not allow it.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)

    response = get_members(server_id, str(uuid.uuid4()))

    assert response.status_code == 403
    assert "detail" in response.json()


def test_get_members_server_not_found():
    """
    CA 4: Non-existent server
    Given the members of a server that does not exist are requested
    When the server processes the request
    Then the system reports that the server was not found.
    """
    response = get_members(str(uuid.uuid4()), str(uuid.uuid4()))

    assert response.status_code == 404
    assert "detail" in response.json()


def test_get_members_only_returns_members_from_that_server():
    """Regression guard: members from another server must not leak into the listing."""
    owner_a = str(uuid.uuid4())
    create_test_server(owner_a)
    owner_b = str(uuid.uuid4())
    server_b_id = create_test_server(owner_b)

    body = get_members(server_b_id, owner_b).json()

    assert body["total"] == 1
    assert [m["user_id"] for m in body["items"]] == [owner_b]
