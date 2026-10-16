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
from app.models.server_invite import ServerInvite
from app.models.server_member import ServerMember
from app.repositories.moderation import ModerationRepository
from tests import db_utils

client = TestClient(app)


def headers_for(user_id: str) -> dict:
    return {"x-user-id": user_id}


def create_test_server(owner_id: str) -> dict:
    response = client.post("/api/v1/servers", data={"name": "Ban Server"}, headers=headers_for(owner_id))
    assert response.status_code == 201, response.json()
    return response.json()


def add_member(server_id: str, user_id: str) -> str:

    async def _add():
        async with db_utils.TestingSessionLocal() as db:
            member = ServerMember(server_id=uuid.UUID(server_id), user_id=user_id)
            db.add(member)
            await db.flush()
            default_role = await db.scalar(
                select(Role).where(Role.server_id == uuid.UUID(server_id), Role.is_default.is_(True))
            )
            db.add(RoleAssignment(server_member_id=member.id, role_id=default_role.id))
            await db.commit()
            return str(member.id)

    return asyncio.run(_add())


def create_role(server_id: str, owner_id: str, name: str, extra: Permission | None = None) -> str:
    response = client.post(f"/api/v1/servers/{server_id}/roles", json={"name": name}, headers=headers_for(owner_id))
    assert response.status_code == 201, response.json()
    role_id = response.json()["id"]
    if extra is not None:
        bitmask = int(DEFAULT_ROLE_PERMISSIONS | extra)
        patch = client.patch(
            f"/api/v1/servers/{server_id}/roles/{role_id}/permissions",
            json={"new_permissions_bitmask": bitmask},
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


def ban(server_id: str, actor_id: str, target_id: str, reason: str | None = None):
    payload = {"user_id": target_id}
    if reason is not None:
        payload["reason"] = reason
    return client.post(f"/api/v1/servers/{server_id}/bans", json=payload, headers=headers_for(actor_id))


def create_invite(server_id: str, owner_id: str) -> str:
    response = client.post(f"/api/v1/servers/{server_id}/invites", json={}, headers=headers_for(owner_id))
    assert response.status_code == 201, response.json()
    return response.json()["code"]


def _run(fn):
    async def _go():
        async with db_utils.TestingSessionLocal() as db:
            return await fn(db)

    return asyncio.run(_go())


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


def banned_events(server_id: str, user_id: str) -> list[OutboxEvent]:
    async def _get(db):
        result = await db.execute(select(OutboxEvent).where(OutboxEvent.routing_key == "member.banned"))
        return [e for e in result.scalars() if e.payload["server_id"] == server_id and e.payload["user_id"] == user_id]

    return _run(_get)


def invite_uses(code: str) -> int:
    return _run(lambda db: db.scalar(select(ServerInvite.uses).where(ServerInvite.code == code)))


def assert_nothing_persisted(server_id: str, target_id: str):
    assert get_ban_row(server_id, target_id) is None
    assert is_member(server_id, target_id)
    assert banned_events(server_id, target_id) == []


# CA 1: Baneo exitoso

def test_ban_member_success():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    target_id = str(uuid.uuid4())
    add_member(server_id, target_id)

    response = ban(server_id, owner_id, target_id, reason="spam")

    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["server_id"] == server_id
    assert body["user_id"] == target_id
    assert body["banned_by"] == owner_id
    assert body["reason"] == "spam"

    assert get_ban_row(server_id, target_id) is not None
    assert not is_member(server_id, target_id)

    members = client.get(f"/api/v1/servers/{server_id}/members", headers=headers_for(owner_id)).json()
    assert target_id not in [m["user_id"] for m in members["items"]]

    servers = client.get("/api/v1/servers", headers=headers_for(target_id)).json()
    assert server_id not in [s["id"] for s in servers]


def test_ban_member_without_reason():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    target_id = str(uuid.uuid4())
    add_member(server_id, target_id)

    response = ban(server_id, owner_id, target_id)

    assert response.status_code == 201, response.json()
    assert response.json()["reason"] is None


def test_ban_removes_member_roles():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    role_id = create_role(server_id, owner_id, "Helper")
    target_id = add_member_with_role(server_id, owner_id, role_id)

    assert ban(server_id, owner_id, target_id).status_code == 201

    response = client.get(f"/api/v1/servers/{server_id}/roles/{role_id}/members", headers=headers_for(owner_id))
    assert response.status_code == 200
    assert response.json() == []


def test_banned_member_loses_channel_access():
    owner_id = str(uuid.uuid4())
    server = create_test_server(owner_id)
    server_id = server["id"]
    channel_id = server["channels"][0]["id"]
    target_id = str(uuid.uuid4())
    add_member(server_id, target_id)

    before = client.get(f"/internal/channels/{channel_id}/can-send", params={"user_id": target_id})
    assert before.status_code == 200

    assert ban(server_id, owner_id, target_id).status_code == 201

    after = client.get(f"/internal/channels/{channel_id}/can-send", params={"user_id": target_id})
    assert after.status_code == 403


def test_banned_user_cannot_rejoin_with_invite():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    target_id = str(uuid.uuid4())
    add_member(server_id, target_id)
    code = create_invite(server_id, owner_id)
    second_code = create_invite(server_id, owner_id)

    assert ban(server_id, owner_id, target_id).status_code == 201

    for invite_code in (code, second_code):
        response = client.post(f"/api/v1/invites/{invite_code}/join", headers=headers_for(target_id))
        assert response.status_code == 403, response.json()
    assert not is_member(server_id, target_id)


def test_banned_join_attempt_does_not_consume_invite_use():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    target_id = str(uuid.uuid4())
    add_member(server_id, target_id)
    code = create_invite(server_id, owner_id)

    assert ban(server_id, owner_id, target_id).status_code == 201
    response = client.post(f"/api/v1/invites/{code}/join", headers=headers_for(target_id))

    assert response.status_code == 403
    assert invite_uses(code) == 0


def test_unbanned_user_can_rejoin():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    target_id = str(uuid.uuid4())
    add_member(server_id, target_id)
    code = create_invite(server_id, owner_id)
    assert ban(server_id, owner_id, target_id).status_code == 201

    unban = client.delete(f"/api/v1/servers/{server_id}/bans/{target_id}", headers=headers_for(owner_id))
    assert unban.status_code == 204

    response = client.post(f"/api/v1/invites/{code}/join", headers=headers_for(target_id))
    assert response.status_code == 200, response.json()
    assert is_member(server_id, target_id)


def test_ban_writes_outbox_event():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    target_id = str(uuid.uuid4())
    add_member(server_id, target_id)

    assert ban(server_id, owner_id, target_id, reason="spam").status_code == 201

    events = banned_events(server_id, target_id)
    assert len(events) == 1
    assert events[0].status == "PENDING"
    assert events[0].payload["banned_by"] == owner_id
    assert events[0].payload["reason"] == "spam"


def test_ban_user_that_is_not_a_member():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    outsider_id = str(uuid.uuid4())
    code = create_invite(server_id, owner_id)

    assert ban(server_id, owner_id, outsider_id).status_code == 201

    response = client.post(f"/api/v1/invites/{code}/join", headers=headers_for(outsider_id))
    assert response.status_code == 403


def test_ban_by_member_with_ban_members_permission():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    target_id = str(uuid.uuid4())
    add_member(server_id, target_id)
    mod_role = create_role(server_id, owner_id, "Moderator", Permission.BAN_MEMBERS)
    mod_id = add_member_with_role(server_id, owner_id, mod_role)

    response = ban(server_id, mod_id, target_id)

    assert response.status_code == 201, response.json()
    assert response.json()["banned_by"] == mod_id


def test_ban_by_administrator():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    target_id = str(uuid.uuid4())
    add_member(server_id, target_id)
    admin_role = create_role(server_id, owner_id, "Admin", Permission.ADMINISTRATOR)
    admin_id = add_member_with_role(server_id, owner_id, admin_role)

    response = ban(server_id, admin_id, target_id)

    assert response.status_code == 201, response.json()


def test_ban_reason_too_long_returns_422():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    target_id = str(uuid.uuid4())
    add_member(server_id, target_id)

    response = ban(server_id, owner_id, target_id, reason="x" * 501)

    assert response.status_code == 422
    assert_nothing_persisted(server_id, target_id)


def test_ban_invalid_body_returns_422():
    """CA 1: El body se valida antes de tocar la base de datos."""
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    url = f"/api/v1/servers/{server_id}/bans"

    for payload in ({}, {"user_id": ""}, {"user_id": "a\x00b"}, {"user_id": "u" * 256}):
        response = client.post(url, json=payload, headers=headers_for(owner_id))
        assert response.status_code == 422, payload


# CA 2: Restriccion por jerarquia

def test_ban_member_with_equal_role_is_rejected():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    mod_role = create_role(server_id, owner_id, "Moderator", Permission.BAN_MEMBERS)
    mod_id = add_member_with_role(server_id, owner_id, mod_role)
    peer_id = add_member_with_role(server_id, owner_id, mod_role)

    response = ban(server_id, mod_id, peer_id)

    assert response.status_code == 403, response.json()
    assert_nothing_persisted(server_id, peer_id)


def test_ban_member_with_higher_role_is_rejected():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    junior_role = create_role(server_id, owner_id, "Junior Mod", Permission.BAN_MEMBERS)
    senior_role = create_role(server_id, owner_id, "Senior Mod", Permission.BAN_MEMBERS)
    junior_id = add_member_with_role(server_id, owner_id, junior_role)
    senior_id = add_member_with_role(server_id, owner_id, senior_role)

    response = ban(server_id, junior_id, senior_id)

    assert response.status_code == 403, response.json()
    assert_nothing_persisted(server_id, senior_id)


def test_administrator_does_not_bypass_hierarchy():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    admin_role = create_role(server_id, owner_id, "Admin", Permission.ADMINISTRATOR)
    boss_role = create_role(server_id, owner_id, "Boss")
    admin_id = add_member_with_role(server_id, owner_id, admin_role)
    boss_id = add_member_with_role(server_id, owner_id, boss_role)

    response = ban(server_id, admin_id, boss_id)

    assert response.status_code == 403, response.json()
    assert_nothing_persisted(server_id, boss_id)


def test_ban_member_with_lower_role_succeeds():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    low_role = create_role(server_id, owner_id, "Regular")
    mod_role = create_role(server_id, owner_id, "Moderator", Permission.BAN_MEMBERS)
    low_id = add_member_with_role(server_id, owner_id, low_role)
    mod_id = add_member_with_role(server_id, owner_id, mod_role)

    response = ban(server_id, mod_id, low_id)

    assert response.status_code == 201, response.json()
    assert not is_member(server_id, low_id)


def test_owner_can_ban_member_with_highest_role():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    boss_role = create_role(server_id, owner_id, "Boss", Permission.ADMINISTRATOR)
    boss_id = add_member_with_role(server_id, owner_id, boss_role)

    response = ban(server_id, owner_id, boss_id)

    assert response.status_code == 201, response.json()


def test_cannot_ban_server_owner():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    admin_role = create_role(server_id, owner_id, "Admin", Permission.ADMINISTRATOR)
    admin_id = add_member_with_role(server_id, owner_id, admin_role)

    response = ban(server_id, admin_id, owner_id)

    assert response.status_code == 400, response.json()
    assert get_ban_row(server_id, owner_id) is None
    assert is_member(server_id, owner_id)


def test_cannot_ban_yourself():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    mod_role = create_role(server_id, owner_id, "Moderator", Permission.BAN_MEMBERS)
    mod_id = add_member_with_role(server_id, owner_id, mod_role)

    response = ban(server_id, mod_id, mod_id)

    assert response.status_code == 400, response.json()
    assert get_ban_row(server_id, mod_id) is None


# CA 3: Sin permisos

def test_ban_without_permission_is_rejected():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    regular_id = str(uuid.uuid4())
    target_id = str(uuid.uuid4())
    add_member(server_id, regular_id)
    add_member(server_id, target_id)

    response = ban(server_id, regular_id, target_id)

    assert response.status_code == 403, response.json()
    assert_nothing_persisted(server_id, target_id)


def test_ban_by_non_member_is_rejected():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    target_id = str(uuid.uuid4())
    add_member(server_id, target_id)

    response = ban(server_id, str(uuid.uuid4()), target_id)

    assert response.status_code == 403, response.json()
    assert_nothing_persisted(server_id, target_id)


def test_unprivileged_user_gets_403_even_when_targeting_owner():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    regular_id = str(uuid.uuid4())
    add_member(server_id, regular_id)

    response = ban(server_id, regular_id, owner_id)

    assert response.status_code == 403, response.json()


def test_ban_permission_granted_through_default_role():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    roles = client.get(f"/api/v1/servers/{server_id}/roles", headers=headers_for(owner_id)).json()
    default_role = next(r for r in roles if r["is_default"])
    patch = client.patch(
        f"/api/v1/servers/{server_id}/roles/{default_role['id']}/permissions",
        json={"new_permissions_bitmask": int(DEFAULT_ROLE_PERMISSIONS | Permission.BAN_MEMBERS)},
        headers=headers_for(owner_id),
    )
    assert patch.status_code == 200
    actor_id = str(uuid.uuid4())
    target_id = str(uuid.uuid4())
    add_member(server_id, actor_id)
    add_member(server_id, target_id)

    response = ban(server_id, actor_id, target_id)

    assert response.status_code == 403, response.json()
    assert_nothing_persisted(server_id, target_id)


# Casos codigo de error

def test_ban_without_user_header_returns_401():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]

    response = client.post(f"/api/v1/servers/{server_id}/bans", json={"user_id": "someone"})

    assert response.status_code == 401


def test_ban_in_nonexistent_server_returns_404():
    response = ban(str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()))

    assert response.status_code == 404


def test_ban_already_banned_user_returns_409():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    mod_role = create_role(server_id, owner_id, "Moderator", Permission.BAN_MEMBERS)
    mod_id = add_member_with_role(server_id, owner_id, mod_role)
    target_id = str(uuid.uuid4())
    add_member(server_id, target_id)
    assert ban(server_id, owner_id, target_id, reason="original").status_code == 201

    response = ban(server_id, mod_id, target_id, reason="otro motivo")

    assert response.status_code == 409, response.json()
    row = get_ban_row(server_id, target_id)
    assert row.banned_by == owner_id
    assert row.reason == "original"
    assert len(banned_events(server_id, target_id)) == 1


def test_ban_race_condition_returns_409_and_rolls_back(monkeypatch):
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)["id"]
    target_id = str(uuid.uuid4())
    add_member(server_id, target_id)

    async def insert_existing_ban(db):
        db.add(ServerBan(server_id=uuid.UUID(server_id), user_id=target_id, banned_by=owner_id))
        await db.commit()

    _run(insert_existing_ban)

    async def not_found(self, db, server_id, user_id):
        return None

    monkeypatch.setattr(ModerationRepository, "get_ban", not_found)

    response = ban(server_id, owner_id, target_id)

    assert response.status_code == 409, response.json()
    assert is_member(server_id, target_id)
    assert banned_events(server_id, target_id) == []
