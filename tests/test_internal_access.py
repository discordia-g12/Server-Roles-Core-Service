"""GET /internal/channels/{id}/access: ver un canal y poder escribir en él son permisos distintos."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.core.permissions import ALL_PERMISSIONS, DEFAULT_ROLE_PERMISSIONS, Permission
from app.main import app
from app.models.channel_permission_override import ChannelPermissionOverride
from app.models.role import Role
from app.models.role_assignment import RoleAssignment
from app.models.server_member import ServerMember
from tests import db_utils

client = TestClient(app)


def headers_for(user_id: str) -> dict:
    return {"x-user-id": user_id}


def _run(fn):
    async def _go():
        async with db_utils.TestingSessionLocal() as db:
            return await fn(db)

    return asyncio.run(_go())


def create_server(owner_id: str) -> tuple[str, str]:
    """Crea un servidor y devuelve (server_id, id del canal de texto por defecto)."""
    response = client.post("/api/v1/servers", data={"name": "Access Server"}, headers=headers_for(owner_id))
    assert response.status_code == 201, response.json()
    body = response.json()
    text_channel = next(ch for ch in body["channels"] if ch["type"] == "text")
    return body["id"], text_channel["id"]


def add_member(server_id: str) -> tuple[str, str]:
    """Agrega un miembro con @everyone y devuelve (user_id, server_member_id)."""
    user_id = str(uuid.uuid4())

    async def _add(db):
        member = ServerMember(server_id=uuid.UUID(server_id), user_id=user_id)
        db.add(member)
        await db.flush()
        default_role = await db.scalar(
            select(Role).where(Role.server_id == uuid.UUID(server_id), Role.is_default.is_(True))
        )
        db.add(RoleAssignment(server_member_id=member.id, role_id=default_role.id))
        await db.commit()
        return str(member.id)

    return user_id, _run(_add)


def set_default_role_permissions(server_id: str, bitmask: int) -> None:
    async def _set(db):
        await db.execute(
            update(Role)
            .where(Role.server_id == uuid.UUID(server_id), Role.is_default.is_(True))
            .values(permissions_bitmask=bitmask)
        )
        await db.commit()

    _run(_set)


def default_role_id(server_id: str) -> uuid.UUID:
    return _run(
        lambda db: db.scalar(select(Role.id).where(Role.server_id == uuid.UUID(server_id), Role.is_default.is_(True)))
    )


def add_override(channel_id: str, *, deny: int = 0, allow: int = 0, role_id=None, server_member_id=None) -> None:
    async def _add(db):
        db.add(
            ChannelPermissionOverride(
                channel_id=uuid.UUID(channel_id),
                role_id=role_id,
                server_member_id=uuid.UUID(server_member_id) if server_member_id else None,
                allow_bitmask=allow,
                deny_bitmask=deny,
            )
        )
        await db.commit()

    _run(_add)


def mute(server_id: str, owner_id: str, user_id: str, duration_seconds: int | None = None):
    payload = {"user_id": user_id}
    if duration_seconds is not None:
        payload["duration_seconds"] = duration_seconds
    response = client.post(f"/api/v1/servers/{server_id}/mutes", json=payload, headers=headers_for(owner_id))
    assert response.status_code == 201, response.json()


def get_access(channel_id: str, user_id: str):
    return client.get(f"/internal/channels/{channel_id}/access", params={"user_id": user_id})


# ---------- Puede ver y escribir ----------


def test_owner_can_view_and_send():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)

    response = get_access(channel_id, owner_id)

    assert response.status_code == 200
    assert response.json() == {
        "server_id": server_id,
        "can_send": True,
        "muted_until": None,
        "can_mention_everyone": True,
        "mentionable_role_ids": [],
        "can_manage_messages": True,
    }


def test_member_with_default_role_can_view_and_send():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    user_id, _ = add_member(server_id)

    response = get_access(channel_id, user_id)

    assert response.status_code == 200
    assert response.json()["can_send"] is True
    assert response.json()["can_manage_messages"] is False


def test_member_with_manage_messages_can_manage_messages():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    user_id, _ = add_member(server_id)
    set_default_role_permissions(server_id, int(DEFAULT_ROLE_PERMISSIONS | Permission.MANAGE_MESSAGES))

    response = get_access(channel_id, user_id)

    assert response.status_code == 200
    assert response.json()["can_manage_messages"] is True


def test_administrator_bypasses_channel_deny():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    user_id, member_id = add_member(server_id)
    set_default_role_permissions(server_id, int(DEFAULT_ROLE_PERMISSIONS | Permission.ADMINISTRATOR))
    add_override(channel_id, deny=int(Permission.VIEW_CHANNELS | Permission.SEND_MESSAGES), server_member_id=member_id)

    response = get_access(channel_id, user_id)

    assert response.status_code == 200
    assert response.json()["can_send"] is True
    assert response.json()["can_manage_messages"] is True


# ---------- Muteado: ve el canal pero no escribe ----------


def test_temporarily_muted_member_can_view_but_not_send():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    user_id, _ = add_member(server_id)
    before = datetime.now(UTC)
    mute(server_id, owner_id, user_id, duration_seconds=600)

    response = get_access(channel_id, user_id)

    assert response.status_code == 200
    body = response.json()
    assert body["can_send"] is False
    assert body["muted_until"].endswith("Z")
    muted_until = datetime.fromisoformat(body["muted_until"].replace("Z", "+00:00"))
    assert before + timedelta(seconds=590) < muted_until < before + timedelta(seconds=610)


def test_indefinitely_muted_member_has_no_muted_until():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    user_id, _ = add_member(server_id)
    mute(server_id, owner_id, user_id)

    response = get_access(channel_id, user_id)

    assert response.status_code == 200
    assert response.json()["can_send"] is False
    assert response.json()["muted_until"] is None


def test_unmuted_member_can_send_again():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    user_id, _ = add_member(server_id)
    mute(server_id, owner_id, user_id, duration_seconds=600)
    unmute = client.delete(f"/api/v1/servers/{server_id}/mutes/{user_id}", headers=headers_for(owner_id))
    assert unmute.status_code == 204

    response = get_access(channel_id, user_id)

    assert response.json()["can_send"] is True
    assert response.json()["muted_until"] is None


def test_muted_until_is_null_when_mute_is_not_the_only_restriction():
    """Sin SEND_MESSAGES, al vencer el mute igual no podría escribir: no se informa el vencimiento."""
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    user_id, _ = add_member(server_id)
    set_default_role_permissions(server_id, int(DEFAULT_ROLE_PERMISSIONS & ~Permission.SEND_MESSAGES))
    mute(server_id, owner_id, user_id, duration_seconds=600)

    response = get_access(channel_id, user_id)

    assert response.status_code == 200
    assert response.json()["can_send"] is False
    assert response.json()["muted_until"] is None


# ---------- Sin SEND_MESSAGES: ve pero no escribe ----------


def test_member_without_send_messages_can_view_but_not_send():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    user_id, _ = add_member(server_id)
    set_default_role_permissions(server_id, int(DEFAULT_ROLE_PERMISSIONS & ~Permission.SEND_MESSAGES))

    response = get_access(channel_id, user_id)

    assert response.status_code == 200
    assert response.json()["can_send"] is False


# ---------- Sin VIEW_CHANNELS: 403 ----------


def test_member_without_view_channels_is_forbidden():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    user_id, _ = add_member(server_id)
    set_default_role_permissions(server_id, int(DEFAULT_ROLE_PERMISSIONS & ~Permission.VIEW_CHANNELS))

    response = get_access(channel_id, user_id)

    assert response.status_code == 403
    assert response.json()["detail"] == "User does not have permission to view this channel"


def test_role_override_denying_view_is_forbidden():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    user_id, _ = add_member(server_id)
    add_override(channel_id, deny=int(Permission.VIEW_CHANNELS), role_id=default_role_id(server_id))

    assert get_access(channel_id, user_id).status_code == 403


def test_member_override_denying_view_is_forbidden():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    user_id, member_id = add_member(server_id)
    add_override(channel_id, deny=int(Permission.VIEW_CHANNELS), server_member_id=member_id)

    assert get_access(channel_id, user_id).status_code == 403


def test_member_override_allow_wins_over_role_deny():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    user_id, member_id = add_member(server_id)
    add_override(channel_id, deny=int(Permission.VIEW_CHANNELS), role_id=default_role_id(server_id))
    add_override(channel_id, allow=int(Permission.VIEW_CHANNELS), server_member_id=member_id)

    assert get_access(channel_id, user_id).status_code == 200


# ---------- Sin acceso al servidor ----------


def test_non_member_is_forbidden():
    owner_id = str(uuid.uuid4())
    _, channel_id = create_server(owner_id)

    response = get_access(channel_id, str(uuid.uuid4()))

    assert response.status_code == 403
    assert "User is not a member" in response.json()["detail"]


def test_banned_user_is_forbidden():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    user_id, _ = add_member(server_id)
    ban = client.post(f"/api/v1/servers/{server_id}/bans", json={"user_id": user_id}, headers=headers_for(owner_id))
    assert ban.status_code == 201, ban.json()

    assert get_access(channel_id, user_id).status_code == 403


def test_unknown_channel_is_not_found():
    response = get_access(str(uuid.uuid4()), str(uuid.uuid4()))

    assert response.status_code == 404
    assert response.json()["detail"] == "Channel not found"


# ---------- can-send no cambia ----------


def test_can_send_still_rejects_muted_member():
    owner_id = str(uuid.uuid4())
    server_id, channel_id = create_server(owner_id)
    user_id, _ = add_member(server_id)
    mute(server_id, owner_id, user_id, duration_seconds=600)

    response = client.get(f"/internal/channels/{channel_id}/can-send", params={"user_id": user_id})

    assert response.status_code == 403
    assert response.json()["detail"] == "User is muted in the server"


# ---------- Qué puede publicar en voz (can-connect) ----------


def create_voice_channel(server_id: str, owner_id: str) -> str:
    response = client.post(
        f"/api/v1/servers/{server_id}/channels",
        json={"name": "voz", "type": "voice"},
        headers=headers_for(owner_id),
    )
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def get_can_connect(channel_id: str, user_id: str):
    return client.get(f"/internal/channels/{channel_id}/can-connect", params={"user_id": user_id})


def test_default_role_can_speak_use_video_and_share_screen():
    owner_id = str(uuid.uuid4())
    server_id, _ = create_server(owner_id)
    channel_id = create_voice_channel(server_id, owner_id)
    user_id, _ = add_member(server_id)

    response = get_can_connect(channel_id, user_id)

    assert response.status_code == 200
    assert response.json() == {
        "can_connect": True,
        "server_id": server_id,
        "can_speak": True,
        "can_video": True,
        "can_screen_share": True,
    }


def test_voice_permissions_are_independent():
    owner_id = str(uuid.uuid4())
    server_id, _ = create_server(owner_id)
    channel_id = create_voice_channel(server_id, owner_id)
    user_id, _ = add_member(server_id)
    set_default_role_permissions(
        server_id, int(DEFAULT_ROLE_PERMISSIONS & ~Permission.SPEAK & ~Permission.SCREEN_SHARE)
    )

    body = get_can_connect(channel_id, user_id).json()

    assert body["can_connect"] is True
    assert body["can_speak"] is False
    assert body["can_video"] is True
    assert body["can_screen_share"] is False


def test_channel_override_can_deny_video():
    owner_id = str(uuid.uuid4())
    server_id, _ = create_server(owner_id)
    channel_id = create_voice_channel(server_id, owner_id)
    user_id, _ = add_member(server_id)
    add_override(channel_id, deny=Permission.VIDEO.value, role_id=default_role_id(server_id))

    body = get_can_connect(channel_id, user_id).json()

    assert body["can_video"] is False
    assert body["can_speak"] is True


def test_muted_member_can_connect_but_not_speak():
    owner_id = str(uuid.uuid4())
    server_id, _ = create_server(owner_id)
    channel_id = create_voice_channel(server_id, owner_id)
    user_id, _ = add_member(server_id)
    mute(server_id, owner_id, user_id, duration_seconds=600)

    response = get_can_connect(channel_id, user_id)

    assert response.status_code == 200
    assert response.json()["can_speak"] is False
    assert response.json()["can_video"] is True


def test_owner_has_every_voice_permission():
    owner_id = str(uuid.uuid4())
    server_id, _ = create_server(owner_id)
    channel_id = create_voice_channel(server_id, owner_id)

    body = get_can_connect(channel_id, owner_id).json()

    assert body["can_speak"] is True
    assert body["can_video"] is True
    assert body["can_screen_share"] is True


def test_member_without_connect_is_still_forbidden():
    owner_id = str(uuid.uuid4())
    server_id, _ = create_server(owner_id)
    channel_id = create_voice_channel(server_id, owner_id)
    user_id, _ = add_member(server_id)
    set_default_role_permissions(server_id, int(DEFAULT_ROLE_PERMISSIONS & ~Permission.CONNECT))

    assert get_can_connect(channel_id, user_id).status_code == 403


# ---------- my_permissions en GET /servers (el front muestra solo lo que puede hacer) ----------


def my_server(user_id: str, server_id: str) -> dict:
    response = client.get("/api/v1/servers", headers=headers_for(user_id))
    assert response.status_code == 200, response.json()
    return next(server for server in response.json() if server["id"] == server_id)


def test_owner_gets_every_permission_in_server_and_channels():
    owner_id = str(uuid.uuid4())
    server_id, _ = create_server(owner_id)

    server = my_server(owner_id, server_id)

    assert server["my_permissions"] == ALL_PERMISSIONS
    assert all(channel["my_permissions"] == ALL_PERMISSIONS for channel in server["channels"])


def test_member_gets_the_permissions_of_their_roles():
    owner_id = str(uuid.uuid4())
    server_id, _ = create_server(owner_id)
    user_id, _ = add_member(server_id)

    server = my_server(user_id, server_id)

    assert server["my_permissions"] == int(DEFAULT_ROLE_PERMISSIONS)
    assert not server["my_permissions"] & Permission.MANAGE_CHANNELS.value


def test_channel_permissions_include_the_channel_overrides():
    owner_id = str(uuid.uuid4())
    server_id, _ = create_server(owner_id)
    voice_id = create_voice_channel(server_id, owner_id)
    user_id, _ = add_member(server_id)
    add_override(voice_id, deny=Permission.CONNECT.value, role_id=default_role_id(server_id))

    server = my_server(user_id, server_id)
    channels = {channel["id"]: channel for channel in server["channels"]}

    assert server["my_permissions"] & Permission.CONNECT.value
    assert not channels[voice_id]["my_permissions"] & Permission.CONNECT.value
    other_voice = next(c for c in server["channels"] if c["type"] == "voice" and c["id"] != voice_id)
    assert other_voice["my_permissions"] & Permission.CONNECT.value


def test_administrator_gets_every_permission():
    owner_id = str(uuid.uuid4())
    server_id, _ = create_server(owner_id)
    user_id, _ = add_member(server_id)
    set_default_role_permissions(server_id, int(DEFAULT_ROLE_PERMISSIONS | Permission.ADMINISTRATOR))

    assert my_server(user_id, server_id)["my_permissions"] == ALL_PERMISSIONS


def test_created_server_includes_my_permissions():
    owner_id = str(uuid.uuid4())
    response = client.post("/api/v1/servers", data={"name": "Nuevo"}, headers=headers_for(owner_id))

    assert response.status_code == 201
    assert response.json()["my_permissions"] == ALL_PERMISSIONS
