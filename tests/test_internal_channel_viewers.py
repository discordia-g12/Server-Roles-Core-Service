"""POST /internal/channels/{id}/viewers: qué usuarios de una lista pueden ver el canal."""

import uuid

from fastapi.testclient import TestClient

from app.core.permissions import Permission
from app.main import app
from app.models.role import Role
from app.models.role_assignment import RoleAssignment
from tests.test_internal_access import (
    _run,
    add_member,
    add_override,
    create_server,
    default_role_id,
    get_access,
    headers_for,
)

client = TestClient(app)
VIEW = Permission.VIEW_CHANNELS.value


def viewers(channel_id, user_ids):
    return client.post(f"/internal/channels/{channel_id}/viewers", json={"user_ids": user_ids})


def ban(server_id, owner_id, user_id):
    response = client.post(
        f"/api/v1/servers/{server_id}/bans", json={"user_id": user_id}, headers=headers_for(owner_id)
    )
    assert response.status_code in (200, 201), response.json()


def give_new_role(server_id: str, member_id: str) -> uuid.UUID:
    async def _go(db):
        role = Role(server_id=uuid.UUID(server_id), name="VIP", permissions_bitmask=0, position=5)
        db.add(role)
        await db.flush()
        db.add(RoleAssignment(server_member_id=uuid.UUID(member_id), role_id=role.id))
        await db.commit()
        return role.id

    return _run(_go)


def test_public_channel_members_only_and_no_banned():
    owner = str(uuid.uuid4())
    server_id, channel_id = create_server(owner)
    a, _ = add_member(server_id)
    banned, _ = add_member(server_id)
    ban(server_id, owner, banned)
    outsider = str(uuid.uuid4())

    response = viewers(channel_id, [a, banned, outsider, owner, a])

    assert response.status_code == 200
    assert sorted(response.json()["user_ids"]) == sorted([a, owner])


def test_private_channel_only_role_members_and_consistent_with_access():
    owner = str(uuid.uuid4())
    server_id, channel_id = create_server(owner)
    plain, _ = add_member(server_id)
    vip, vip_member = add_member(server_id)
    vip_role = give_new_role(server_id, vip_member)
    add_override(channel_id, deny=VIEW, role_id=default_role_id(server_id))
    add_override(channel_id, allow=VIEW, role_id=vip_role)
    candidates = [owner, plain, vip]

    response = viewers(channel_id, candidates)

    assert sorted(response.json()["user_ids"]) == sorted([owner, vip])
    for user in candidates:
        assert (user in response.json()["user_ids"]) == (get_access(channel_id, user).status_code == 200)


def test_member_override_allows_and_denies():
    owner = str(uuid.uuid4())
    server_id, channel_id = create_server(owner)
    allowed, allowed_member = add_member(server_id)
    denied, denied_member = add_member(server_id)
    other, _ = add_member(server_id)
    add_override(channel_id, deny=VIEW, role_id=default_role_id(server_id))
    add_override(channel_id, allow=VIEW, server_member_id=allowed_member)
    # Un deny de miembro tampoco puede revivir lo que ya negó el rol
    add_override(channel_id, deny=VIEW, server_member_id=denied_member)

    response = viewers(channel_id, [allowed, denied, other])

    assert response.json()["user_ids"] == [allowed]


def test_member_deny_on_public_channel():
    owner = str(uuid.uuid4())
    server_id, channel_id = create_server(owner)
    denied, denied_member = add_member(server_id)
    ok, _ = add_member(server_id)
    add_override(channel_id, deny=VIEW, server_member_id=denied_member)

    assert viewers(channel_id, [denied, ok]).json()["user_ids"] == [ok]


def test_unknown_channel_404():
    assert viewers(str(uuid.uuid4()), ["x"]).status_code == 404


def test_more_than_5000_is_422():
    owner = str(uuid.uuid4())
    _, channel_id = create_server(owner)
    assert viewers(channel_id, [str(i) for i in range(5001)]).status_code == 422


def test_empty_list_returns_empty():
    owner = str(uuid.uuid4())
    _, channel_id = create_server(owner)
    response = viewers(channel_id, [])
    assert response.status_code == 200
    assert response.json() == {"user_ids": []}
