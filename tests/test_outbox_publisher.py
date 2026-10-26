"""Worker que relaya el outbox a RabbitMQ: se prueba contra la DB de test con un exchange falso."""

import json
import uuid

import aio_pika
import pytest
from sqlalchemy import select

import tests.db_utils as db_utils
from app.models.outbox_event import OutboxEvent
from app.workers import outbox_publisher


class FakeExchange:
    """Registers the publsihed stuff insted of sending it to RabbitMQ"""

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.published: list[tuple[aio_pika.Message, str]] = []

    async def publish(self, message: aio_pika.Message, routing_key: str) -> None:
        if self.fail:
            raise ConnectionError("RabbitMQ no disponible")
        self.published.append((message, routing_key))


@pytest.fixture(autouse=True)
def use_test_db(monkeypatch):
    monkeypatch.setattr(outbox_publisher, "AsyncSessionLocal", db_utils.TestingSessionLocal)


async def create_event(db_session, server_id: str) -> uuid.UUID:
    event = OutboxEvent(routing_key="channel.created", payload={"server_id": server_id, "channel_id": "c-1"})
    db_session.add(event)
    await db_session.commit()
    return event.id


async def get_event(event_id: uuid.UUID) -> OutboxEvent:
    async with db_utils.TestingSessionLocal() as db:
        return (await db.execute(select(OutboxEvent).where(OutboxEvent.id == event_id))).scalar_one()


async def publish_all(exchange: FakeExchange) -> None:
    """Publshes until empty queue."""
    while await outbox_publisher._publish_pending_events(exchange):
        pass


@pytest.mark.anyio
async def test_publishes_pending_event_and_marks_it_published(db_session):
    server_id = str(uuid.uuid4())
    event_id = await create_event(db_session, server_id)
    exchange = FakeExchange()

    await publish_all(exchange)

    messages = {message.message_id: (message, routing_key) for message, routing_key in exchange.published}
    message, routing_key = messages[str(event_id)]
    assert routing_key == "channel.created"
    assert json.loads(message.body) == {"server_id": server_id, "channel_id": "c-1"}

    event = await get_event(event_id)
    assert event.status == outbox_publisher.PUBLISHED
    assert event.published_at is not None


@pytest.mark.anyio
async def test_published_event_is_not_sent_twice(db_session):
    event_id = await create_event(db_session, str(uuid.uuid4()))
    await publish_all(FakeExchange())

    second_run = FakeExchange()
    await publish_all(second_run)

    assert str(event_id) not in [message.message_id for message, _ in second_run.published]


@pytest.mark.anyio
async def test_event_stays_pending_if_broker_fails(db_session):
    """If it fails to publish, it si not marked as published: it then retiries (at-least-once)."""
    event_id = await create_event(db_session, str(uuid.uuid4()))

    with pytest.raises(ConnectionError):
        await outbox_publisher._publish_pending_events(FakeExchange(fail=True))

    event = await get_event(event_id)
    assert event.status == outbox_publisher.PENDING
    assert event.published_at is None


def test_build_message_is_persistent_and_idempotent():
    event = OutboxEvent(
        id=uuid.uuid4(), routing_key="category.deleted", payload={"server_id": "srv-1", "category_id": "cat-1"}
    )

    message = outbox_publisher._build_message(event)

    assert message.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
    assert message.message_id == str(event.id)
    assert message.type == "category.deleted"
    assert message.content_type == "application/json"
    assert message.headers == {"server_id": "srv-1"}
