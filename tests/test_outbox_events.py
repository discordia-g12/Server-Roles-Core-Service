"""Cada cambio en canales y categorías deja su evento en el outbox, en el mismo commit (ADR-0004)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models.outbox_event import OutboxEvent
from app.models.server_member import ServerMember

client = TestClient(app)


def create_test_server(owner_id: str) -> str:
    response = client.post("/api/v1/servers", data={"name": "Outbox Test Server"}, headers={"x-user-id": owner_id})
    return response.json()["id"]


async def events_for_server(db_session, routing_key: str, server_id: str) -> list[OutboxEvent]:
    result = await db_session.execute(select(OutboxEvent).where(OutboxEvent.routing_key == routing_key))
    return [event for event in result.scalars() if event.payload.get("server_id") == server_id]


@pytest.mark.anyio
async def test_channel_lifecycle_writes_outbox_events(db_session):
    owner_id = str(uuid.uuid4())
    headers = {"x-user-id": owner_id}
    server_id = create_test_server(owner_id)

    channel_id = client.post(
        f"/api/v1/servers/{server_id}/channels", json={"name": "events", "type": "text"}, headers=headers
    ).json()["id"]
    client.patch(f"/api/v1/servers/{server_id}/channels/{channel_id}", json={"topic": "hola"}, headers=headers)
    client.delete(f"/api/v1/servers/{server_id}/channels/{channel_id}", headers=headers)

    for routing_key in ("channel.created", "channel.updated", "channel.deleted"):
        events = await events_for_server(db_session, routing_key, server_id)
        assert len(events) == 1, routing_key
        assert events[0].payload["channel_id"] == channel_id
        assert events[0].status == "PENDING"


@pytest.mark.anyio
async def test_category_lifecycle_writes_outbox_events(db_session):
    owner_id = str(uuid.uuid4())
    headers = {"x-user-id": owner_id}
    server_id = create_test_server(owner_id)

    category_id = client.post(
        f"/api/v1/servers/{server_id}/categories", json={"name": "EVENTS"}, headers=headers
    ).json()["id"]
    client.delete(f"/api/v1/servers/{server_id}/categories/{category_id}", headers=headers)

    for routing_key in ("category.created", "category.deleted"):
        events = await events_for_server(db_session, routing_key, server_id)
        assert len(events) == 1, routing_key
        assert events[0].payload["category_id"] == category_id


@pytest.mark.anyio
async def test_reorders_write_outbox_events(db_session):
    owner_id = str(uuid.uuid4())
    headers = {"x-user-id": owner_id}
    server_id = create_test_server(owner_id)
    first = client.post(f"/api/v1/servers/{server_id}/categories", json={"name": "A"}, headers=headers).json()["id"]
    second = client.post(f"/api/v1/servers/{server_id}/categories", json={"name": "B"}, headers=headers).json()["id"]
    server = next(s for s in client.get("/api/v1/servers", headers=headers).json() if s["id"] == server_id)

    client.put(
        f"/api/v1/servers/{server_id}/categories/order", json={"category_ids": [second, first]}, headers=headers
    )
    client.put(
        f"/api/v1/servers/{server_id}/channels/order",
        json={"channels": [{"id": c["id"], "category_id": None} for c in reversed(server["channels"])]},
        headers=headers,
    )

    assert len(await events_for_server(db_session, "categories.reordered", server_id)) == 1
    assert len(await events_for_server(db_session, "channels.reordered", server_id)) == 1


@pytest.mark.anyio
async def test_rejected_change_does_not_write_outbox_event(db_session):
    """Si el cambio se rechaza (403), no queda ningún evento: se escriben en la misma transacción."""
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)

    response = client.post(
        f"/api/v1/servers/{server_id}/categories",
        json={"name": "NOPE"},
        headers={"x-user-id": str(uuid.uuid4())},
    )

    assert response.status_code == 403
    assert await events_for_server(db_session, "category.created", server_id) == []


@pytest.mark.anyio
async def test_member_moderation_writes_outbox_events(db_session):
    owner_id = str(uuid.uuid4())
    headers = {"x-user-id": owner_id}
    server_id = create_test_server(owner_id)
    target_user_id = str(uuid.uuid4())
    db_session.add(ServerMember(server_id=uuid.UUID(server_id), user_id=target_user_id))
    await db_session.commit()

    mute_res = client.post(
        f"/api/v1/servers/{server_id}/mutes",
        json={"user_id": target_user_id, "duration_seconds": 60, "reason": "spam"},
        headers=headers,
    )
    assert mute_res.status_code == 201
    events = await events_for_server(db_session, "member.muted", server_id)
    assert len(events) == 1
    assert events[0].payload["user_id"] == target_user_id

    unmute_res = client.delete(f"/api/v1/servers/{server_id}/mutes/{target_user_id}", headers=headers)
    assert unmute_res.status_code == 204
    events = await events_for_server(db_session, "member.unmuted", server_id)
    assert len(events) == 1

    ban_res = client.post(
        f"/api/v1/servers/{server_id}/bans",
        json={"user_id": target_user_id, "reason": "severe violation"},
        headers=headers,
    )
    assert ban_res.status_code == 201
    events = await events_for_server(db_session, "member.banned", server_id)
    assert len(events) == 1
    assert events[0].payload["user_id"] == target_user_id

    unban_res = client.delete(f"/api/v1/servers/{server_id}/bans/{target_user_id}", headers=headers)
    assert unban_res.status_code == 204
    events = await events_for_server(db_session, "member.unbanned", server_id)
    assert len(events) == 1


@pytest.mark.anyio
async def test_member_leave_writes_outbox_event(db_session):
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    member_user_id = str(uuid.uuid4())
    db_session.add(ServerMember(server_id=uuid.UUID(server_id), user_id=member_user_id))
    await db_session.commit()

    leave_res = client.delete(f"/api/v1/servers/{server_id}/leave", headers={"x-user-id": member_user_id})
    assert leave_res.status_code == 204
    events = await events_for_server(db_session, "member.left", server_id)
    assert len(events) == 1
    assert events[0].payload["user_id"] == member_user_id


@pytest.mark.anyio
async def test_member_kicked_writes_outbox_event(db_session):
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    target_user_id = str(uuid.uuid4())
    db_session.add(ServerMember(server_id=uuid.UUID(server_id), user_id=target_user_id))
    await db_session.commit()

    kick_res = client.delete(
        f"/api/v1/servers/{server_id}/members/{target_user_id}",
        headers={"x-user-id": owner_id},
    )
    assert kick_res.status_code == 204
    events = await events_for_server(db_session, "member.kicked", server_id)
    assert len(events) == 1
    assert events[0].payload["user_id"] == target_user_id
    assert events[0].payload["kicked_by"] == owner_id


@pytest.mark.anyio
async def test_role_lifecycle_writes_outbox_events(db_session):
    owner_id = str(uuid.uuid4())
    headers = {"x-user-id": owner_id}
    server_id = create_test_server(owner_id)
    member_user_id = str(uuid.uuid4())
    db_session.add(ServerMember(server_id=uuid.UUID(server_id), user_id=member_user_id))
    await db_session.commit()

    role_res = client.post(f"/api/v1/servers/{server_id}/roles", json={"name": "Moderator"}, headers=headers)
    assert role_res.status_code == 201
    role_id = role_res.json()["id"]

    patch_res = client.patch(
        f"/api/v1/servers/{server_id}/roles/{role_id}/permissions",
        json={"new_permissions_bitmask": 1024},
        headers=headers,
    )
    assert patch_res.status_code == 200
    events = await events_for_server(db_session, "role.permissions_updated", server_id)
    assert len(events) == 1

    assign_res = client.put(
        f"/api/v1/servers/{server_id}/roles/{role_id}/members/{member_user_id}",
        headers=headers,
    )
    assert assign_res.status_code == 204
    events = await events_for_server(db_session, "member.role_assigned", server_id)
    assert len(events) == 1

    remove_res = client.delete(
        f"/api/v1/servers/{server_id}/roles/{role_id}/members/{member_user_id}",
        headers=headers,
    )
    assert remove_res.status_code == 204
    events = await events_for_server(db_session, "member.role_removed", server_id)
    assert len(events) == 1

    delete_res = client.delete(f"/api/v1/servers/{server_id}/roles/{role_id}", headers=headers)
    assert delete_res.status_code == 204
    events = await events_for_server(db_session, "role.deleted", server_id)
    assert len(events) == 1
