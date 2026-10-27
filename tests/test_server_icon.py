"""Cambiar y quitar el ícono de un servidor existente (PUT / DELETE /servers/{id}/icon).

S3 no se toca: el fixture fake_storage de conftest.py registra las subidas y los borrados.
"""

import asyncio
import io
import uuid

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.core.permissions import Permission
from app.exceptions import StorageUnavailableError
from app.main import app
from app.models.outbox_event import OutboxEvent
from tests import db_utils
from tests.test_server_bans import add_member, add_member_with_role, create_role, headers_for

client = TestClient(app)


def _png(color: str = "blue") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 32), color=color).save(buffer, format="PNG")
    return buffer.getvalue()


def _create_server(owner_id: str, with_icon: bool = False) -> dict:
    files = {"icon": ("icon.png", _png("red"), "image/png")} if with_icon else None
    response = client.post("/api/v1/servers", data={"name": "Icon Server"}, files=files, headers=headers_for(owner_id))
    assert response.status_code == 201, response.json()
    return response.json()


def _put_icon(server_id: str, user_id: str, content: bytes | None = None, content_type: str = "image/png"):
    files = {"icon": ("icon.png", content if content is not None else _png(), content_type)}
    return client.put(f"/api/v1/servers/{server_id}/icon", files=files, headers=headers_for(user_id))


def _server_updated_events(server_id: str) -> list[OutboxEvent]:
    async def _query():
        async with db_utils.TestingSessionLocal() as db:
            rows = await db.scalars(select(OutboxEvent).where(OutboxEvent.routing_key == "server.updated"))
            return [e for e in rows.all() if e.payload.get("server_id") == server_id]

    return asyncio.run(_query())


def test_owner_replaces_icon_and_old_one_is_deleted(fake_storage):
    owner = str(uuid.uuid4())
    server = _create_server(owner, with_icon=True)
    old_url = server["icon_url"]

    response = _put_icon(server["id"], owner)

    assert response.status_code == 200, response.json()
    body = response.json()
    new_upload = fake_storage["uploaded"][-1]
    assert new_upload["prefix"] == "server-icons"
    assert body["icon_url"] == new_upload["url"] != old_url
    # El anterior se borra recién con el cambio guardado
    assert fake_storage["deleted"] == [old_url]
    # La respuesta es el servidor completo (con sus canales), igual que al crearlo
    assert body["id"] == server["id"]
    assert len(body["channels"]) == 2

    listed = client.get("/api/v1/servers", headers=headers_for(owner)).json()
    assert next(s for s in listed if s["id"] == server["id"])["icon_url"] == body["icon_url"]


def test_icon_change_emits_server_updated_event():
    owner = str(uuid.uuid4())
    server = _create_server(owner)

    _put_icon(server["id"], owner)
    client.delete(f"/api/v1/servers/{server['id']}/icon", headers=headers_for(owner))

    assert len(_server_updated_events(server["id"])) == 2


def test_member_with_manage_server_can_change_icon():
    owner = str(uuid.uuid4())
    server = _create_server(owner)
    role_id = create_role(server["id"], owner, "Admins", Permission.MANAGE_SERVER)
    manager = add_member_with_role(server["id"], owner, role_id)

    response = _put_icon(server["id"], manager)

    assert response.status_code == 200, response.json()


def test_member_with_administrator_can_change_icon():
    owner = str(uuid.uuid4())
    server = _create_server(owner)
    role_id = create_role(server["id"], owner, "Admin", Permission.ADMINISTRATOR)
    admin = add_member_with_role(server["id"], owner, role_id)

    assert _put_icon(server["id"], admin).status_code == 200


def test_member_without_permission_gets_403_and_nothing_is_uploaded(fake_storage):
    owner = str(uuid.uuid4())
    server = _create_server(owner)
    member = str(uuid.uuid4())
    add_member(server["id"], member)

    put = _put_icon(server["id"], member)
    delete = client.delete(f"/api/v1/servers/{server['id']}/icon", headers=headers_for(member))

    assert put.status_code == 403
    assert "MANAGE_SERVER" in put.json()["detail"]
    assert delete.status_code == 403
    assert fake_storage["uploaded"] == []


def test_non_member_gets_403():
    owner = str(uuid.uuid4())
    server = _create_server(owner)

    assert _put_icon(server["id"], str(uuid.uuid4())).status_code == 403


def test_unknown_server_gets_404():
    assert _put_icon(str(uuid.uuid4()), str(uuid.uuid4())).status_code == 404


def test_invalid_image_is_rejected_and_icon_is_kept(fake_storage):
    owner = str(uuid.uuid4())
    server = _create_server(owner, with_icon=True)

    response = _put_icon(server["id"], owner, content=b"not an image")

    assert response.status_code == 400
    assert "Use JPEG, PNG or WebP" in response.json()["detail"]
    assert len(fake_storage["uploaded"]) == 1  # solo el de la creación
    assert fake_storage["deleted"] == []


def test_storage_down_returns_503_and_icon_is_kept(fake_storage, monkeypatch):
    owner = str(uuid.uuid4())
    server = _create_server(owner, with_icon=True)

    def broken_upload(*args, **kwargs):
        raise StorageUnavailableError()

    monkeypatch.setattr("app.services.storage.upload_image", broken_upload)

    response = _put_icon(server["id"], owner)

    assert response.status_code == 503
    listed = client.get("/api/v1/servers", headers=headers_for(owner)).json()
    assert next(s for s in listed if s["id"] == server["id"])["icon_url"] == server["icon_url"]
    assert fake_storage["deleted"] == []


def test_db_failure_deletes_the_new_icon_and_keeps_the_old_one(fake_storage, monkeypatch):
    from app.repositories.server import ServerRepository

    owner = str(uuid.uuid4())
    server = _create_server(owner, with_icon=True)

    async def broken_set_icon(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(ServerRepository, "set_icon", broken_set_icon)

    try:
        _put_icon(server["id"], owner)
    except RuntimeError:
        pass

    new_url = fake_storage["uploaded"][-1]["url"]
    assert fake_storage["deleted"] == [new_url]
    assert server["icon_url"] not in fake_storage["deleted"]


def test_remove_icon_clears_it_and_deletes_the_file(fake_storage):
    owner = str(uuid.uuid4())
    server = _create_server(owner, with_icon=True)

    response = client.delete(f"/api/v1/servers/{server['id']}/icon", headers=headers_for(owner))

    assert response.status_code == 200, response.json()
    assert response.json()["icon_url"] is None
    assert fake_storage["deleted"] == [server["icon_url"]]


def test_remove_icon_without_icon_is_a_no_op(fake_storage):
    owner = str(uuid.uuid4())
    server = _create_server(owner)

    response = client.delete(f"/api/v1/servers/{server['id']}/icon", headers=headers_for(owner))

    assert response.status_code == 200
    assert response.json()["icon_url"] is None
    assert fake_storage["deleted"] == []
    assert _server_updated_events(server["id"]) == []
