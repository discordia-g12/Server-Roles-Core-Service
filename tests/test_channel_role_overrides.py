"""#18 Sobrescribir permisos de un rol en un canal específico.

/api/v1/servers/{server_id}/channels/{channel_id}/permissions/roles[/{role_id}]
"""

import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.permissions import DEFAULT_ROLE_PERMISSIONS, Permission
from app.main import app
from app.models.outbox_event import OutboxEvent
from app.models.role import Role
from app.models.role_assignment import RoleAssignment
from app.models.server_member import ServerMember
from tests import db_utils

client = TestClient(app)

SEND = Permission.SEND_MESSAGES.value
VIEW = Permission.VIEW_CHANNELS.value


def headers_for(user_id: str) -> dict:
    return {"x-user-id": user_id}


def _run(fn):
    async def _go():
        async with db_utils.TestingSessionLocal() as db:
            return await fn(db)

    return asyncio.run(_go())


def create_server(owner_id: str) -> tuple[str, str]:
    """Crea un servidor y devuelve (server_id, id del canal de texto por defecto)."""
    response = client.post("/api/v1/servers", data={"name": "Overrides Server"}, headers=headers_for(owner_id))
    assert response.status_code == 201, response.json()
    body = response.json()
    text_channel = next(ch for ch in body["channels"] if ch["type"] == "text")
    return body["id"], text_channel["id"]


def create_channel(server_id: str, owner_id: str, name: str = "otro") -> str:
    response = client.post(
        f"/api/v1/servers/{server_id}/channels", json={"name": name, "type": "text"}, headers=headers_for(owner_id)
    )
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def create_role(server_id: str, owner_id: str, name: str = "Moderador") -> str:
    response = client.post(f"/api/v1/servers/{server_id}/roles", json={"name": name}, headers=headers_for(owner_id))
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def default_role_id(server_id: str) -> str:
    role_id = _run(
        lambda db: db.scalar(select(Role.id).where(Role.server_id == uuid.UUID(server_id), Role.is_default.is_(True)))
    )
    return str(role_id)


def add_member(server_id: str, extra_role_id: str | None = None) -> str:
    """Agrega un miembro con el rol por defecto (y otro rol si viene) y devuelve su user_id."""
    user_id = str(uuid.uuid4())
    role_ids = [default_role_id(server_id)] + ([extra_role_id] if extra_role_id else [])

    async def _add(db):
        member = ServerMember(server_id=uuid.UUID(server_id), user_id=user_id)
        db.add(member)
        await db.flush()
        for role_id in role_ids:
            db.add(RoleAssignment(server_member_id=member.id, role_id=uuid.UUID(role_id)))
        await db.commit()

    _run(_add)
    return user_id


def set_override(server_id: str, channel_id: str, role_id: str, user_id: str, *, allow: int = 0, deny: int = 0):
    return client.put(
        f"/api/v1/servers/{server_id}/channels/{channel_id}/permissions/roles/{role_id}",
        json={"allow_bitmask": allow, "deny_bitmask": deny},
        headers=headers_for(user_id),
    )


def list_overrides(server_id: str, channel_id: str, user_id: str):
    return client.get(
        f"/api/v1/servers/{server_id}/channels/{channel_id}/permissions/roles", headers=headers_for(user_id)
    )


def delete_override(server_id: str, channel_id: str, role_id: str, user_id: str):
    return client.delete(
        f"/api/v1/servers/{server_id}/channels/{channel_id}/permissions/roles/{role_id}",
        headers=headers_for(user_id),
    )


def can_send(channel_id: str, user_id: str) -> bool:
    response = client.get(f"/internal/channels/{channel_id}/access", params={"user_id": user_id})
    assert response.status_code == 200, response.json()
    return response.json()["can_send"]


# ---------- CA 1: Sobrescritura exitosa ----------


def test_override_applies_only_in_that_channel():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    other_channel_id = create_channel(server_id, owner_id)
    everyone_id = default_role_id(server_id)
    member_id = add_member(server_id)

    response = set_override(server_id, channel_id, everyone_id, owner_id, deny=SEND)

    assert response.status_code == 200, response.json()
    assert response.json() == {
        "channel_id": channel_id,
        "role_id": everyone_id,
        "allow_bitmask": 0,
        "deny_bitmask": SEND,
    }
    assert can_send(channel_id, member_id) is False
    assert can_send(other_channel_id, member_id) is True


def test_override_does_not_change_the_role_permissions():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    everyone_id = default_role_id(server_id)

    set_override(server_id, channel_id, everyone_id, owner_id, deny=SEND)

    roles = client.get(f"/api/v1/servers/{server_id}/roles", headers=headers_for(owner_id)).json()
    everyone = next(r for r in roles if r["id"] == everyone_id)
    assert everyone["permissions_bitmask"] == int(DEFAULT_ROLE_PERMISSIONS)


def test_override_can_allow_a_permission_the_role_lacks():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    role_id = create_role(server_id, owner_id)
    member_id = add_member(server_id, role_id)
    everyone_id = default_role_id(server_id)
    # Nadie escribe en el canal salvo el rol con la excepción a favor
    set_override(server_id, channel_id, everyone_id, owner_id, deny=SEND)
    set_override(server_id, channel_id, role_id, owner_id, allow=SEND)

    assert can_send(channel_id, member_id) is True


def test_put_replaces_the_existing_override():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    everyone_id = default_role_id(server_id)
    set_override(server_id, channel_id, everyone_id, owner_id, deny=SEND)

    response = set_override(server_id, channel_id, everyone_id, owner_id, deny=VIEW)

    assert response.status_code == 200
    overrides = list_overrides(server_id, channel_id, owner_id).json()
    assert overrides == [{"channel_id": channel_id, "role_id": everyone_id, "allow_bitmask": 0, "deny_bitmask": VIEW}]


def test_list_returns_only_that_channel_overrides():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    other_channel_id = create_channel(server_id, owner_id)
    everyone_id = default_role_id(server_id)
    set_override(server_id, other_channel_id, everyone_id, owner_id, deny=SEND)

    assert list_overrides(server_id, channel_id, owner_id).json() == []
    assert len(list_overrides(server_id, other_channel_id, owner_id).json()) == 1


def test_delete_restores_the_role_permissions_in_the_channel():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    everyone_id = default_role_id(server_id)
    member_id = add_member(server_id)
    set_override(server_id, channel_id, everyone_id, owner_id, deny=SEND)

    response = delete_override(server_id, channel_id, everyone_id, owner_id)

    assert response.status_code == 204
    assert can_send(channel_id, member_id) is True
    assert list_overrides(server_id, channel_id, owner_id).json() == []


def test_delete_without_override_returns_404():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)

    response = delete_override(server_id, channel_id, default_role_id(server_id), owner_id)

    assert response.status_code == 404


def test_member_with_manage_roles_can_override():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    manager_role_id = create_role(server_id, owner_id, "Gestor")
    client.patch(
        f"/api/v1/servers/{server_id}/roles/{manager_role_id}/permissions",
        json={"new_permissions_bitmask": Permission.MANAGE_ROLES.value},
        headers=headers_for(owner_id),
    )
    manager_id = add_member(server_id, manager_role_id)

    response = set_override(server_id, channel_id, default_role_id(server_id), manager_id, deny=SEND)

    assert response.status_code == 200, response.json()


def test_override_writes_outbox_event():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    everyone_id = default_role_id(server_id)

    set_override(server_id, channel_id, everyone_id, owner_id, deny=SEND)
    delete_override(server_id, channel_id, everyone_id, owner_id)

    events = _run(
        lambda db: db.scalars(
            select(OutboxEvent).where(OutboxEvent.routing_key == "role.channel_permissions_updated")
        )
    ).all()
    mine = [e.payload for e in events if e.payload["channel_id"] == channel_id]
    assert [(p["new_allow_bitmask"], p["new_deny_bitmask"]) for p in mine] == [(0, SEND), (0, 0)]
    assert all(p["server_id"] == server_id and p["role_id"] == everyone_id for p in mine)
    assert all(p["updated_by"] == owner_id for p in mine)


# ---------- CA 2: Sin permisos ----------


def test_member_without_permissions_cannot_override():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    everyone_id = default_role_id(server_id)
    member_id = add_member(server_id)

    assert set_override(server_id, channel_id, everyone_id, member_id, allow=SEND).status_code == 403
    assert list_overrides(server_id, channel_id, member_id).status_code == 403
    assert delete_override(server_id, channel_id, everyone_id, member_id).status_code == 403


def test_non_member_cannot_override():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)

    response = set_override(server_id, channel_id, default_role_id(server_id), str(uuid.uuid4()), deny=SEND)

    assert response.status_code == 403


# ---------- Validaciones ----------


def test_allow_and_deny_same_permission_is_rejected():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)

    response = set_override(server_id, channel_id, default_role_id(server_id), owner_id, allow=SEND, deny=SEND)

    assert response.status_code == 422


def test_administrator_cannot_be_overridden():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)

    response = set_override(
        server_id, channel_id, default_role_id(server_id), owner_id, allow=Permission.ADMINISTRATOR.value
    )

    assert response.status_code == 400


def test_unknown_permission_bits_are_rejected():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)

    response = set_override(server_id, channel_id, default_role_id(server_id), owner_id, deny=1 << 40)

    assert response.status_code == 400


def test_channel_of_another_server_returns_404():
    owner_id = str(uuid.uuid4())
    server_id, _ = create_server(owner_id)
    _, foreign_channel_id = create_server(owner_id)

    response = set_override(server_id, foreign_channel_id, default_role_id(server_id), owner_id, deny=SEND)

    assert response.status_code == 404


def test_role_of_another_server_returns_404():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    other_server_id, _ = create_server(owner_id)

    response = set_override(server_id, channel_id, default_role_id(other_server_id), owner_id, deny=SEND)

    assert response.status_code == 404
