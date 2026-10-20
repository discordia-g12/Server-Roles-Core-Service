import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.permissions import DEFAULT_ROLE_PERMISSIONS, Permission
from app.main import app
from app.models.outbox_event import OutboxEvent
from app.models.role import Role
from app.models.role_assignment import RoleAssignment
from app.models.server_ban import ServerBan
from app.models.server_member import ServerMember
from tests import db_utils

client = TestClient(app)


def headers_for(user_id: str) -> dict:
    return {"x-user-id": user_id}


def create_test_server(owner_id: str) -> dict:
    response = client.post("/api/v1/servers", data={"name": "Unban Server"}, headers=headers_for(owner_id))
    assert response.status_code == 201, response.json()
    return response.json()


def _run(fn):
    async def _go():
        async with db_utils.TestingSessionLocal() as db:
            return await fn(db)

    return asyncio.run(_go())


def add_member(server_id: str, user_id: str) -> None:
    async def _add(db):
        member = ServerMember(server_id=uuid.UUID(server_id), user_id=user_id)
        db.add(member)
        await db.flush()
        default_role = await db.scalar(
            select(Role).where(Role.server_id == uuid.UUID(server_id), Role.is_default.is_(True))
        )
        db.add(RoleAssignment(server_member_id=member.id, role_id=default_role.id))
        await db.commit()

    _run(_add)


def create_role(server_id: str, owner_id: str, name: str, extra: Permission) -> str:
    response = client.post(f"/api/v1/servers/{server_id}/roles", json={"name": name}, headers=headers_for(owner_id))
    assert response.status_code == 201, response.json()
    role_id = response.json()["id"]
    patch = client.patch(
        f"/api/v1/servers/{server_id}/roles/{role_id}/permissions",
        json={"new_permissions_bitmask": int(DEFAULT_ROLE_PERMISSIONS | extra)},
        headers=headers_for(owner_id),
    )
    assert patch.status_code == 200, patch.json()
    return role_id


def add_member_with_role(server_id: str, owner_id: str, role_id: str) -> str:
    user_id = str(uuid.uuid4())
    add_member(server_id, user_id)
    response = client.put(
        f"/api/v1/servers/{server_id}/roles/{role_id}/members/{user_id}", headers=headers_for(owner_id)
    )
    assert response.status_code == 204, response.json()
    return user_id


def create_invite(server_id: str, owner_id: str) -> str:
    response = client.post(f"/api/v1/servers/{server_id}/invites", json={}, headers=headers_for(owner_id))
    assert response.status_code == 201, response.json()
    return response.json()["code"]


def ban(server_id: str, actor_id: str, target_id: str):
    return client.post(
        f"/api/v1/servers/{server_id}/bans", json={"user_id": target_id}, headers=headers_for(actor_id)
    )


def get_ban_row(server_id: str, user_id: str) -> ServerBan | None:
    return _run(
        lambda db: db.scalar(
            select(ServerBan).where(ServerBan.server_id == uuid.UUID(server_id), ServerBan.user_id == user_id)
        )
    )


def is_member(server_id: str, user_id: str) -> bool:
    row = _run(
        lambda db: db.scalar(
            select(ServerMember.id).where(
                ServerMember.server_id == uuid.UUID(server_id), ServerMember.user_id == user_id
            )
        )
    )
    return row is not None


def unban(server_id: str, actor_id: str, target_id: str):
    return client.delete(f"/api/v1/servers/{server_id}/bans/{target_id}", headers=headers_for(actor_id))


def join(code: str, user_id: str):
    return client.post(f"/api/v1/invites/{code}/join", headers=headers_for(user_id))


def unbanned_events(server_id: str, user_id: str) -> list[OutboxEvent]:
    async def _get(db):
        result = await db.execute(select(OutboxEvent).where(OutboxEvent.routing_key == "member.unbanned"))
        return [e for e in result.scalars() if e.payload["server_id"] == server_id and e.payload["user_id"] == user_id]

    return _run(_get)


def banned_server(owner_id: str) -> tuple[str, str]:
    """Creates a server with a member that is then banned. Returns (server_id, banned_user_id)."""
    server_id = create_test_server(owner_id)["id"]
    target_id = str(uuid.uuid4())
    add_member(server_id, target_id)
    assert ban(server_id, owner_id, target_id).status_code == 201
    return server_id, target_id


# CA 1: Revocacion exitosa

def test_owner_unbans_user_and_user_can_rejoin_with_invite():
    owner_id = str(uuid.uuid4())
    server_id, target_id = banned_server(owner_id)
    code = create_invite(server_id, owner_id)

    response = unban(server_id, owner_id, target_id)

    assert response.status_code == 204
    assert get_ban_row(server_id, target_id) is None
    assert join(code, target_id).status_code == 200
    assert is_member(server_id, target_id)


def test_unban_by_member_with_ban_members_permission():
    owner_id = str(uuid.uuid4())
    server_id, target_id = banned_server(owner_id)
    mod_role = create_role(server_id, owner_id, "Moderator", Permission.BAN_MEMBERS)
    mod_id = add_member_with_role(server_id, owner_id, mod_role)

    response = unban(server_id, mod_id, target_id)

    assert response.status_code == 204, response.json()
    assert get_ban_row(server_id, target_id) is None


def test_unban_by_administrator():
    owner_id = str(uuid.uuid4())
    server_id, target_id = banned_server(owner_id)
    admin_role = create_role(server_id, owner_id, "Admin", Permission.ADMINISTRATOR)
    admin_id = add_member_with_role(server_id, owner_id, admin_role)

    response = unban(server_id, admin_id, target_id)

    assert response.status_code == 204, response.json()
    assert get_ban_row(server_id, target_id) is None


def test_unban_does_not_readd_user_as_member():
    owner_id = str(uuid.uuid4())
    server_id, target_id = banned_server(owner_id)

    assert unban(server_id, owner_id, target_id).status_code == 204

    # Revoking the ban only allows rejoining; the user still needs a valid invite.
    assert not is_member(server_id, target_id)


def test_unban_writes_outbox_event():
    owner_id = str(uuid.uuid4())
    server_id, target_id = banned_server(owner_id)

    assert unban(server_id, owner_id, target_id).status_code == 204

    events = unbanned_events(server_id, target_id)
    assert len(events) == 1
    assert events[0].status == "PENDING"


def test_unban_only_affects_the_given_server():
    owner_id = str(uuid.uuid4())
    server_a, target_id = banned_server(owner_id)
    server_b = create_test_server(owner_id)["id"]
    add_member(server_b, target_id)
    assert ban(server_b, owner_id, target_id).status_code == 201

    assert unban(server_a, owner_id, target_id).status_code == 204

    assert get_ban_row(server_a, target_id) is None
    assert get_ban_row(server_b, target_id) is not None


def test_unban_user_that_is_not_banned_returns_404():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]

    response = unban(server_id, owner_id, str(uuid.uuid4()))

    assert response.status_code == 404, response.json()


def test_second_unban_returns_404_and_emits_a_single_event():
    owner_id = str(uuid.uuid4())
    server_id, target_id = banned_server(owner_id)

    assert unban(server_id, owner_id, target_id).status_code == 204
    assert unban(server_id, owner_id, target_id).status_code == 404

    assert len(unbanned_events(server_id, target_id)) == 1


def test_unban_in_nonexistent_server_returns_404():
    response = unban(str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()))

    assert response.status_code == 404


# CA 2: Sin permisos

def assert_ban_kept(server_id: str, target_id: str):
    assert get_ban_row(server_id, target_id) is not None
    assert unbanned_events(server_id, target_id) == []


def test_unban_without_permission_is_rejected():
    owner_id = str(uuid.uuid4())
    server_id, target_id = banned_server(owner_id)
    regular_id = str(uuid.uuid4())
    add_member(server_id, regular_id)
    code = create_invite(server_id, owner_id)

    response = unban(server_id, regular_id, target_id)

    assert response.status_code == 403, response.json()
    assert_ban_kept(server_id, target_id)
    assert join(code, target_id).status_code == 403


def test_unban_with_only_kick_permission_is_rejected():
    owner_id = str(uuid.uuid4())
    server_id, target_id = banned_server(owner_id)
    kick_role = create_role(server_id, owner_id, "Kicker", Permission.KICK_MEMBERS)
    kicker_id = add_member_with_role(server_id, owner_id, kick_role)

    response = unban(server_id, kicker_id, target_id)

    assert response.status_code == 403, response.json()
    assert_ban_kept(server_id, target_id)


def test_unban_by_non_member_is_rejected():
    owner_id = str(uuid.uuid4())
    server_id, target_id = banned_server(owner_id)

    response = unban(server_id, str(uuid.uuid4()), target_id)

    assert response.status_code == 403, response.json()
    assert_ban_kept(server_id, target_id)


def test_banned_user_cannot_unban_themselves():
    owner_id = str(uuid.uuid4())
    server_id, target_id = banned_server(owner_id)

    response = unban(server_id, target_id, target_id)

    assert response.status_code == 403, response.json()
    assert_ban_kept(server_id, target_id)


def test_unprivileged_user_gets_403_even_if_user_is_not_banned():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    regular_id = str(uuid.uuid4())
    add_member(server_id, regular_id)

    # 403 (not 404) so a user without permission can't find out who is banned.
    response = unban(server_id, regular_id, str(uuid.uuid4()))

    assert response.status_code == 403, response.json()


def test_unban_without_user_header_returns_401():
    owner_id = str(uuid.uuid4())
    server_id, target_id = banned_server(owner_id)

    response = client.delete(f"/api/v1/servers/{server_id}/bans/{target_id}")

    assert response.status_code == 401
    assert_ban_kept(server_id, target_id)
