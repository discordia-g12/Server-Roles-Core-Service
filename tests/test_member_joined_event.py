"""Al unirse con una invitación, `member.joined` en el outbox con el canal de bienvenida (Chat publica
ahí "se unió …"): el primer canal de texto de la barra lateral que ve @everyone."""

import uuid

import pytest

from app.core.permissions import Permission
from tests.test_internal_access import add_override, client, create_server, default_role_id, headers_for
from tests.test_outbox_events import events_for_server


def create_invite(server_id: str, owner_id: str) -> str:
    response = client.post(f"/api/v1/servers/{server_id}/invites", json={"max_uses": 10}, headers=headers_for(owner_id))
    assert response.status_code == 201, response.json()
    return response.json()["code"]


def join(code: str, user_id: str) -> None:
    response = client.post(f"/api/v1/invites/{code}/join", headers=headers_for(user_id))
    assert response.status_code in (200, 201), response.json()


def create_text_channel(server_id: str, owner_id: str, name: str) -> str:
    response = client.post(
        f"/api/v1/servers/{server_id}/channels", json={"name": name, "type": "text"}, headers=headers_for(owner_id)
    )
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def hide_from_everyone(server_id: str, channel_id: str) -> None:
    add_override(channel_id, deny=int(Permission.VIEW_CHANNELS), role_id=default_role_id(server_id))


async def joined_events(db_session, server_id: str):
    return await events_for_server(db_session, "member.joined", server_id)


@pytest.mark.anyio
async def test_join_writes_member_joined_with_the_first_text_channel(db_session):
    owner_id = str(uuid.uuid4())
    server_id, general_id = create_server(owner_id)
    user_id = str(uuid.uuid4())

    join(create_invite(server_id, owner_id), user_id)

    events = await joined_events(db_session, server_id)
    assert len(events) == 1
    assert events[0].payload == {"server_id": server_id, "user_id": user_id, "channel_id": general_id}
    assert events[0].status == "PENDING"


@pytest.mark.anyio
async def test_welcome_channel_skips_channels_everyone_cannot_see(db_session):
    owner_id = str(uuid.uuid4())
    server_id, general_id = create_server(owner_id)
    hide_from_everyone(server_id, general_id)
    lobby_id = create_text_channel(server_id, owner_id, "lobby")

    join(create_invite(server_id, owner_id), str(uuid.uuid4()))

    events = await joined_events(db_session, server_id)
    assert events[0].payload["channel_id"] == lobby_id


@pytest.mark.anyio
async def test_without_a_channel_everyone_can_see_the_event_has_no_channel(db_session):
    owner_id = str(uuid.uuid4())
    server_id, general_id = create_server(owner_id)
    hide_from_everyone(server_id, general_id)

    join(create_invite(server_id, owner_id), str(uuid.uuid4()))

    events = await joined_events(db_session, server_id)
    assert len(events) == 1
    assert events[0].payload["channel_id"] is None


@pytest.mark.anyio
async def test_joining_again_does_not_announce_twice(db_session):
    owner_id = str(uuid.uuid4())
    server_id, _ = create_server(owner_id)
    code = create_invite(server_id, owner_id)
    user_id = str(uuid.uuid4())

    join(code, user_id)
    join(code, user_id)

    assert len(await joined_events(db_session, server_id)) == 1
