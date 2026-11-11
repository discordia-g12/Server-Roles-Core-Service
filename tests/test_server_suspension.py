"""Suspender un servidor completo (backoffice) y levantar la suspensión. docs/ADR-002-Suspension-de-Servidores.md"""

import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models.outbox_event import OutboxEvent
from app.models.server import Server
from app.models.server_member import ServerMember
from tests import db_utils

client = TestClient(app)

STAFF = {"x-user-id": "auth0|staff", "x-user-role": "staff"}
SUSPENDED_TYPE = "https://discordia.app/problems/server-suspended"


def as_user(user_id: str) -> dict:
    return {"x-user-id": user_id}


def _run(fn):
    async def _go():
        async with db_utils.TestingSessionLocal() as db:
            return await fn(db)

    return asyncio.run(_go())


def create_server(owner_id: str) -> dict:
    response = client.post("/api/v1/servers", data={"name": "Gaming Nocturno"}, headers=as_user(owner_id))
    assert response.status_code == 201, response.json()
    return response.json()


def add_member(server_id: str) -> str:
    user_id = f"auth0|{uuid.uuid4()}"

    async def _add(db):
        db.add(ServerMember(server_id=uuid.UUID(server_id), user_id=user_id))
        await db.commit()

    _run(_add)
    return user_id


def suspend(server_id: str, reason: str = "denuncia en investigación", headers: dict = STAFF):
    return client.post(f"/api/v1/admin/servers/{server_id}/suspension", json={"reason": reason}, headers=headers)


def lift(server_id: str, headers: dict = STAFF):
    return client.delete(f"/api/v1/admin/servers/{server_id}/suspension", headers=headers)


def events(server_id: str, routing_key: str) -> list[OutboxEvent]:
    async def _get(db):
        result = await db.execute(select(OutboxEvent).where(OutboxEvent.routing_key == routing_key))
        return [e for e in result.scalars().all() if e.payload.get("server_id") == server_id]

    return _run(_get)


def text_and_voice_channels(server: dict) -> tuple[str, str]:
    text = next(ch["id"] for ch in server["channels"] if ch["type"] == "text")
    voice = next(ch["id"] for ch in server["channels"] if ch["type"] == "voice")
    return text, voice


# ---------- CA 1: suspensión exitosa ----------


def test_staff_suspends_a_server_by_id():
    owner = f"auth0|{uuid.uuid4()}"
    server = create_server(owner)
    add_member(server["id"])

    response = suspend(server["id"])

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == server["id"]
    assert body["is_suspended"] is True
    assert body["suspension_reason"] == "denuncia en investigación"
    assert body["suspended_by"] == "auth0|staff"
    assert body["member_count"] == 2  # el dueño y el miembro

    [event] = events(server["id"], "server.suspended")
    _, voice = text_and_voice_channels(server)
    assert event.payload["voice_channel_ids"] == [voice]


def test_no_member_can_use_a_suspended_server_not_even_the_owner():
    owner = f"auth0|{uuid.uuid4()}"
    server = create_server(owner)
    member = add_member(server["id"])
    suspend(server["id"])

    for user in (owner, member):
        for method, path in [
            ("get", f"/api/v1/servers/{server['id']}/members"),
            ("get", f"/api/v1/servers/{server['id']}/roles"),
            ("get", f"/api/v1/servers/{server['id']}/categories"),
            ("post", f"/api/v1/servers/{server['id']}/invites"),
            ("get", f"/api/v1/servers/{server['id']}/bans"),
            ("get", f"/api/v1/servers/{server['id']}/transfers/pending"),
        ]:
            body = {} if method == "post" else None
            response = client.request(method.upper(), path, headers=as_user(user), json=body)
            assert response.status_code == 403, (path, response.json())
            assert response.json()["type"] == SUSPENDED_TYPE


def test_chat_and_voice_access_is_denied_while_suspended():
    owner = f"auth0|{uuid.uuid4()}"
    server = create_server(owner)
    text, voice = text_and_voice_channels(server)
    suspend(server["id"])

    access = client.get(f"/internal/channels/{text}/access", params={"user_id": owner})
    connect = client.get(f"/internal/channels/{voice}/can-connect", params={"user_id": owner})
    visible = client.get(f"/internal/users/{owner}/visible-channels")

    assert access.status_code == 403
    assert access.json()["type"] == SUSPENDED_TYPE
    assert connect.status_code == 403
    assert text not in visible.json()["channel_ids"]


def test_audit_log_permissions_are_denied_while_suspended():
    # Notification-Audit-Metrics pregunta acá antes de mostrar el registro de auditoría del servidor
    owner = f"auth0|{uuid.uuid4()}"
    server = create_server(owner)
    suspend(server["id"])

    response = client.get(f"/internal/servers/{server['id']}/members/{owner}/permissions")

    assert response.status_code == 403
    assert response.json()["type"] == SUSPENDED_TYPE


def test_member_still_sees_the_server_marked_suspended_without_its_content():
    owner = f"auth0|{uuid.uuid4()}"
    server = create_server(owner)
    member = add_member(server["id"])
    suspend(server["id"])

    listed = next(s for s in client.get("/api/v1/servers", headers=as_user(member)).json() if s["id"] == server["id"])

    assert listed["is_suspended"] is True
    assert listed["name"] == "Gaming Nocturno"
    assert listed["channels"] == []
    assert listed["categories"] == []


def test_content_is_kept_while_suspended():
    owner = f"auth0|{uuid.uuid4()}"
    server = create_server(owner)
    suspend(server["id"])

    async def _channels(db):
        stored = await db.scalar(select(Server).where(Server.id == uuid.UUID(server["id"])))
        return {str(ch.id) for ch in stored.channels}

    assert _run(_channels) == {ch["id"] for ch in server["channels"]}


def test_nobody_joins_a_suspended_server_with_an_invite():
    owner = f"auth0|{uuid.uuid4()}"
    server = create_server(owner)
    invite = client.post(f"/api/v1/servers/{server['id']}/invites", json={}, headers=as_user(owner))
    assert invite.status_code == 201, invite.json()
    suspend(server["id"])

    response = client.post(f"/api/v1/invites/{invite.json()['code']}/join", headers=as_user(f"auth0|{uuid.uuid4()}"))

    assert response.status_code == 403
    assert response.json()["type"] == SUSPENDED_TYPE


def test_members_can_still_leave_a_suspended_server():
    owner = f"auth0|{uuid.uuid4()}"
    server = create_server(owner)
    member = add_member(server["id"])
    suspend(server["id"])

    response = client.delete(f"/api/v1/servers/{server['id']}/leave", headers=as_user(member))

    assert response.status_code == 204


# ---------- CA 2: levantar la suspensión ----------


def test_lifting_the_suspension_restores_normal_access():
    owner = f"auth0|{uuid.uuid4()}"
    server = create_server(owner)
    member = add_member(server["id"])
    text, _ = text_and_voice_channels(server)
    suspend(server["id"])

    response = lift(server["id"])

    assert response.status_code == 200
    assert response.json()["is_suspended"] is False
    assert response.json()["suspension_reason"] is None
    assert client.get(f"/api/v1/servers/{server['id']}/members", headers=as_user(member)).status_code == 200
    # El dueño: el miembro de prueba se agrega sin el rol por defecto, así que no tiene VIEW_CHANNELS
    assert client.get(f"/internal/channels/{text}/access", params={"user_id": owner}).status_code == 200
    listed = next(s for s in client.get("/api/v1/servers", headers=as_user(member)).json() if s["id"] == server["id"])
    assert listed["is_suspended"] is False
    assert len(listed["channels"]) == len(server["channels"])
    assert len(events(server["id"], "server.unsuspended")) == 1


def test_staff_lists_suspended_servers():
    server = create_server(f"auth0|{uuid.uuid4()}")
    other = create_server(f"auth0|{uuid.uuid4()}")
    suspend(server["id"])

    ids = [s["id"] for s in client.get("/api/v1/admin/servers/suspended", headers=STAFF).json()]

    assert server["id"] in ids
    assert other["id"] not in ids


# ---------- Errores y permisos ----------


def test_unknown_server_is_404():
    assert suspend(str(uuid.uuid4())).status_code == 404
    assert lift(str(uuid.uuid4())).status_code == 404


def test_suspending_twice_or_lifting_an_active_server_is_409():
    server = create_server(f"auth0|{uuid.uuid4()}")

    assert lift(server["id"]).status_code == 409
    assert suspend(server["id"]).status_code == 201
    assert suspend(server["id"]).status_code == 409


def test_reason_is_required():
    server = create_server(f"auth0|{uuid.uuid4()}")

    assert suspend(server["id"], reason="").status_code == 422


def test_only_staff_can_suspend_lift_or_list():
    owner = f"auth0|{uuid.uuid4()}"
    server = create_server(owner)
    not_staff = {"x-user-id": owner, "x-user-role": "user"}

    for response in (
        suspend(server["id"], headers=not_staff),
        lift(server["id"], headers=as_user(owner)),
        client.get("/api/v1/admin/servers/suspended", headers=not_staff),
    ):
        assert response.status_code == 403
        assert response.json()["type"] == "https://discordia.app/problems/staff-only"

    assert suspend(server["id"], headers={}).status_code == 401
