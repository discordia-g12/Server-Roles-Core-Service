"""Cada cambio en canales y categorías deja su evento en el outbox, en el mismo commit (ADR-0004)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models.outbox_event import OutboxEvent

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
