"""GET /internal/users/{id}/visible-channels: los canales de texto que el usuario puede ver (no leídos en Chat)."""

import uuid

from app.core.permissions import DEFAULT_ROLE_PERMISSIONS, Permission
from tests.test_internal_access import (
    add_member,
    add_override,
    client,
    create_server,
    create_voice_channel,
    default_role_id,
    headers_for,
    set_default_role_permissions,
)


def visible_channels(user_id: str, server_id: str | None = None) -> set[str]:
    params = {"server_id": server_id} if server_id else None
    response = client.get(f"/internal/users/{user_id}/visible-channels", params=params)
    assert response.status_code == 200, response.json()
    return set(response.json()["channel_ids"])


def create_text_channel(server_id: str, owner_id: str, name: str = "otro") -> str:
    response = client.post(
        f"/api/v1/servers/{server_id}/channels",
        json={"name": name, "type": "text"},
        headers=headers_for(owner_id),
    )
    assert response.status_code == 201, response.json()
    return response.json()["id"]


# ---------- Qué canales aparecen ----------


def test_owner_sees_the_text_channels_but_not_the_voice_channels():
    owner_id = str(uuid.uuid4())
    server_id, text_id = create_server(owner_id)
    voice_id = create_voice_channel(server_id, owner_id)

    channels = visible_channels(owner_id)

    assert text_id in channels
    assert voice_id not in channels


def test_member_sees_the_text_channels_of_every_server():
    owner_id = str(uuid.uuid4())
    first_id, first_text = create_server(owner_id)
    second_id, second_text = create_server(owner_id)
    extra_text = create_text_channel(second_id, owner_id)
    user_id, _ = add_member(first_id)
    # Otro usuario, solo en el segundo servidor
    other_user, _ = add_member(second_id)

    assert visible_channels(user_id) == {first_text}
    assert visible_channels(other_user) == {second_text, extra_text}


def test_user_without_servers_gets_an_empty_list():
    assert visible_channels(str(uuid.uuid4())) == set()


def test_channels_of_servers_where_the_user_is_not_a_member_are_not_included():
    owner_id = str(uuid.uuid4())
    _, foreign_text = create_server(owner_id)
    own_id, own_text = create_server(str(uuid.uuid4()))
    user_id, _ = add_member(own_id)

    channels = visible_channels(user_id)

    assert own_text in channels
    assert foreign_text not in channels


# ---------- Filtro por servidor (búsqueda de mensajes) ----------


def test_server_filter_returns_only_the_channels_of_that_server():
    owner_id = str(uuid.uuid4())
    first_id, first_text = create_server(owner_id)
    second_id, second_text = create_server(owner_id)
    extra_text = create_text_channel(second_id, owner_id)

    assert visible_channels(owner_id, first_id) == {first_text}
    assert visible_channels(owner_id, second_id) == {second_text, extra_text}


def test_server_filter_of_a_server_where_the_user_is_not_a_member_is_empty():
    server_id, _ = create_server(str(uuid.uuid4()))

    assert visible_channels(str(uuid.uuid4()), server_id) == set()


def test_server_filter_still_hides_channels_without_view_channels():
    owner_id = str(uuid.uuid4())
    server_id, text_id = create_server(owner_id)
    hidden_id = create_text_channel(server_id, owner_id, "privado")
    user_id, _ = add_member(server_id)
    add_override(hidden_id, deny=int(Permission.VIEW_CHANNELS), role_id=default_role_id(server_id))

    assert visible_channels(user_id, server_id) == {text_id}


def test_server_filter_must_be_a_uuid():
    response = client.get(f"/internal/users/{uuid.uuid4()}/visible-channels", params={"server_id": "nope"})

    assert response.status_code == 422


# ---------- Permisos ----------


def test_role_without_view_channels_sees_nothing():
    owner_id = str(uuid.uuid4())
    server_id, _ = create_server(owner_id)
    user_id, _ = add_member(server_id)
    set_default_role_permissions(server_id, int(DEFAULT_ROLE_PERMISSIONS & ~Permission.VIEW_CHANNELS))

    assert visible_channels(user_id) == set()


def test_channel_override_hides_only_that_channel():
    owner_id = str(uuid.uuid4())
    server_id, text_id = create_server(owner_id)
    hidden_id = create_text_channel(server_id, owner_id, "privado")
    user_id, _ = add_member(server_id)
    add_override(hidden_id, deny=int(Permission.VIEW_CHANNELS), role_id=default_role_id(server_id))

    assert visible_channels(user_id) == {text_id}


def test_member_override_allow_wins_over_role_deny():
    owner_id = str(uuid.uuid4())
    server_id, text_id = create_server(owner_id)
    user_id, member_id = add_member(server_id)
    add_override(text_id, deny=int(Permission.VIEW_CHANNELS), role_id=default_role_id(server_id))
    add_override(text_id, allow=int(Permission.VIEW_CHANNELS), server_member_id=member_id)

    assert text_id in visible_channels(user_id)


def test_administrator_sees_channels_hidden_by_overrides():
    owner_id = str(uuid.uuid4())
    server_id, text_id = create_server(owner_id)
    user_id, member_id = add_member(server_id)
    set_default_role_permissions(server_id, int(DEFAULT_ROLE_PERMISSIONS | Permission.ADMINISTRATOR))
    add_override(text_id, deny=int(Permission.VIEW_CHANNELS), server_member_id=member_id)

    assert text_id in visible_channels(user_id)


# ---------- Ya no es miembro ----------


def test_banned_user_no_longer_sees_the_server_channels():
    owner_id = str(uuid.uuid4())
    server_id, text_id = create_server(owner_id)
    user_id, _ = add_member(server_id)
    ban = client.post(f"/api/v1/servers/{server_id}/bans", json={"user_id": user_id}, headers=headers_for(owner_id))
    assert ban.status_code == 201, ban.json()

    assert text_id not in visible_channels(user_id)


def test_kicked_user_no_longer_sees_the_server_channels():
    owner_id = str(uuid.uuid4())
    server_id, text_id = create_server(owner_id)
    user_id, _ = add_member(server_id)
    kick = client.delete(f"/api/v1/servers/{server_id}/members/{user_id}", headers=headers_for(owner_id))
    assert kick.status_code == 204

    assert text_id not in visible_channels(user_id)
