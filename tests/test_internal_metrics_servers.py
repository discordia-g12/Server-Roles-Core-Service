"""GET /internal/metrics/servers: servidores creados en [from, to), para las métricas del backoffice."""

import uuid
from datetime import datetime

from sqlalchemy import update

from app.models.server import Server
from tests.test_internal_access import _run, client, create_server

# Un período en el pasado: ningún otro test crea servidores ahí (todos usan now())
BASE = datetime(2001, 3, 10, 12, 0, 0)


def create_server_at(created_at: datetime) -> str:
    server_id, _ = create_server(str(uuid.uuid4()))

    async def _set(db):
        await db.execute(update(Server).where(Server.id == uuid.UUID(server_id)).values(created_at=created_at))
        await db.commit()

    _run(_set)
    return server_id


def servers_created(from_: str, to: str):
    return client.get("/internal/metrics/servers", params={"from": from_, "to": to})


def test_counts_only_the_servers_created_inside_the_range():
    create_server_at(datetime(2001, 3, 9, 23, 59, 59))  # antes
    create_server_at(datetime(2001, 3, 10, 0, 0, 0))  # borde `from`: entra
    create_server_at(datetime(2001, 3, 10, 15, 30, 0))
    create_server_at(datetime(2001, 3, 11, 0, 0, 0))  # borde `to`: no entra
    create_server_at(datetime(2001, 3, 12, 8, 0, 0))  # después

    response = servers_created("2001-03-10T00:00:00Z", "2001-03-11T00:00:00Z")

    assert response.status_code == 200, response.json()
    assert response.json() == {
        "from": "2001-03-10T00:00:00.000Z",
        "to": "2001-03-11T00:00:00.000Z",
        "serversCreated": 2,
    }


def test_to_is_excluded():
    create_server_at(datetime(2002, 1, 1, 0, 0, 0))

    assert servers_created("2001-12-31T00:00:00Z", "2002-01-01T00:00:00Z").json()["serversCreated"] == 0
    assert servers_created("2001-12-31T00:00:00Z", "2002-01-01T00:00:00.001Z").json()["serversCreated"] == 1


def test_suspended_servers_are_counted():
    server_id = create_server_at(datetime(2003, 6, 1, 10, 0, 0))

    async def _suspend(db):
        await db.execute(
            update(Server)
            .where(Server.id == uuid.UUID(server_id))
            .values(suspended_at=datetime(2003, 6, 2), suspended_by="staff", suspension_reason="spam")
        )
        await db.commit()

    _run(_suspend)

    assert servers_created("2003-06-01T00:00:00Z", "2003-06-02T00:00:00Z").json()["serversCreated"] == 1


def test_offsets_are_converted_to_utc():
    create_server_at(datetime(2004, 5, 5, 2, 0, 0))  # 23:00 del 4/5 en Buenos Aires

    response = servers_created("2004-05-04T22:00:00-03:00", "2004-05-05T00:00:00-03:00")

    assert response.status_code == 200, response.json()
    assert response.json() == {
        "from": "2004-05-05T01:00:00.000Z",
        "to": "2004-05-05T03:00:00.000Z",
        "serversCreated": 1,
    }


def test_empty_range_returns_zero():
    response = servers_created("1990-01-01T00:00:00Z", "1990-02-01T00:00:00Z")

    assert response.status_code == 200, response.json()
    assert response.json()["serversCreated"] == 0


def test_from_equal_to_to_is_400():
    response = servers_created("2001-03-10T00:00:00Z", "2001-03-10T00:00:00Z")

    assert response.status_code == 400
    assert response.json()["detail"] == "'from' must be earlier than 'to'."


def test_from_after_to_is_400():
    assert servers_created("2001-03-11T00:00:00Z", "2001-03-10T00:00:00Z").status_code == 400


def test_invalid_dates_are_422():
    assert servers_created("ayer", "2001-03-10T00:00:00Z").status_code == 422
    assert client.get("/internal/metrics/servers", params={"from": "2001-03-10T00:00:00Z"}).status_code == 422
