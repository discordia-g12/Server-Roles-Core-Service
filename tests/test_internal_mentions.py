"""Menciones (#46): lo que Chat necesita de Core para validar y contar menciones de rol y @everyone.

- `/internal/channels/{id}/access`: `can_mention_everyone` y `mentionable_role_ids` (al enviar).
- `/internal/users/{id}/visible-channels`: `role_ids` del usuario (al contar `mentionCount`).
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.core.permissions import DEFAULT_ROLE_PERMISSIONS, Permission
from app.main import app
from app.models.role import Role
from app.models.role_assignment import RoleAssignment
from app.models.server_member import ServerMember
from tests.test_internal_access import (
    _run,
    add_member,
    add_override,
    create_server,
    default_role_id,
    get_access,
    headers_for,
    set_default_role_permissions,
)

client = TestClient(app)


def create_role(server_id: str, owner_id: str, name: str) -> str:
    response = client.post(f"/api/v1/servers/{server_id}/roles", json={"name": name}, headers=headers_for(owner_id))
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def assign_role(server_id: str, owner_id: str, role_id: str, user_id: str) -> None:
    response = client.put(
        f"/api/v1/servers/{server_id}/roles/{role_id}/members/{user_id}", headers=headers_for(owner_id)
    )
    assert response.status_code == 204, response.text


def set_role_permissions(role_id: str, permissions: int) -> None:
    async def _set(db):
        await db.execute(update(Role).where(Role.id == uuid.UUID(role_id)).values(permissions_bitmask=permissions))
        await db.commit()

    _run(_set)


def join(server_id: str, user_id: str) -> None:
    """Suma un usuario existente a otro servidor, con el rol por defecto."""

    async def _join(db):
        member = ServerMember(server_id=uuid.UUID(server_id), user_id=user_id)
        db.add(member)
        await db.flush()
        default = await db.scalar(
            select(Role).where(Role.server_id == uuid.UUID(server_id), Role.is_default.is_(True))
        )
        db.add(RoleAssignment(server_member_id=member.id, role_id=default.id))
        await db.commit()

    _run(_join)


def visible(user_id: str) -> dict:
    response = client.get(f"/internal/users/{user_id}/visible-channels")
    assert response.status_code == 200, response.json()
    return response.json()


# ---------- /access: quién puede mencionar a @everyone y a roles ----------


def test_owner_can_mention_everyone_and_gets_the_roles_without_the_default():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    role_id = create_role(server_id, owner_id, "Soporte")

    body = get_access(channel_id, owner_id).json()

    assert body["can_mention_everyone"] is True
    assert body["mentionable_role_ids"] == [role_id]
    assert str(default_role_id(server_id)) not in body["mentionable_role_ids"]


def test_member_with_default_permissions_cannot_mention_everyone():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    create_role(server_id, owner_id, "Soporte")
    user_id, _ = add_member(server_id)

    body = get_access(channel_id, user_id).json()

    assert body["can_mention_everyone"] is False
    assert body["mentionable_role_ids"] == []


def test_member_with_a_role_that_grants_mention_everyone_can():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    role_id = create_role(server_id, owner_id, "Anuncios")
    set_role_permissions(role_id, int(DEFAULT_ROLE_PERMISSIONS | Permission.MENTION_EVERYONE))
    user_id, _ = add_member(server_id)
    assign_role(server_id, owner_id, role_id, user_id)

    body = get_access(channel_id, user_id).json()

    assert body["can_mention_everyone"] is True
    assert body["mentionable_role_ids"] == [role_id]


def test_channel_override_can_deny_mention_everyone():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    set_default_role_permissions(server_id, int(DEFAULT_ROLE_PERMISSIONS | Permission.MENTION_EVERYONE))
    user_id, member_id = add_member(server_id)
    add_override(channel_id, deny=int(Permission.MENTION_EVERYONE), server_member_id=member_id)

    body = get_access(channel_id, user_id).json()

    assert body["can_mention_everyone"] is False


def test_administrator_can_mention_everyone():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    set_default_role_permissions(server_id, int(DEFAULT_ROLE_PERMISSIONS | Permission.ADMINISTRATOR))
    user_id, _ = add_member(server_id)

    assert get_access(channel_id, user_id).json()["can_mention_everyone"] is True


def test_roles_of_another_server_are_not_mentionable():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    other_server_id, _ = create_server(owner_id)
    foreign_role = create_role(other_server_id, owner_id, "Ajeno")

    body = get_access(channel_id, owner_id).json()

    assert foreign_role not in body["mentionable_role_ids"]


# ---------- /visible-channels: roles del usuario ----------


def test_visible_channels_include_the_user_roles_of_every_server_without_defaults():
    owner_id = str(uuid.uuid4())
    first_id, _ = create_server(owner_id)
    second_id, _ = create_server(owner_id)
    first_role = create_role(first_id, owner_id, "Soporte")
    second_role = create_role(second_id, owner_id, "Mods")
    unassigned = create_role(second_id, owner_id, "Nadie")
    user_id, _ = add_member(first_id)
    join(second_id, user_id)
    assign_role(first_id, owner_id, first_role, user_id)
    assign_role(second_id, owner_id, second_role, user_id)

    role_ids = set(visible(user_id)["role_ids"])

    assert role_ids == {first_role, second_role}
    assert unassigned not in role_ids
    assert str(default_role_id(first_id)) not in role_ids


def test_user_without_servers_gets_no_roles():
    assert visible(str(uuid.uuid4())) == {"channel_ids": [], "role_ids": []}
