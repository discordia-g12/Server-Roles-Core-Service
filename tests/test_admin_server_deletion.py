"""Eliminar un servidor desde el backoffice (solo staff)."""

import asyncio
import io
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.main import app
from app.models.category import Category
from app.models.channel import Channel
from app.models.outbox_event import OutboxEvent
from app.models.role import Role
from app.models.server import Server
from app.models.server_invite import ServerInvite
from app.models.server_member import ServerMember
from tests import db_utils

client = TestClient(app)

STAFF = {"x-user-id": "auth0|staff", "x-user-role": "staff"}


def _run(fn):
    async def _go():
        async with db_utils.TestingSessionLocal() as db:
            return await fn(db)

    return asyncio.run(_go())


def _create_server(owner_id: str, name: str = "Servidor Infractor") -> dict:
    response = client.post("/api/v1/servers", data={"name": name}, headers={"x-user-id": owner_id})
    assert response.status_code == 201, response.json()
    return response.json()


def _add_member(server_id: str, user_id: str) -> None:
    async def _add(db):
        db.add(ServerMember(server_id=uuid.UUID(server_id), user_id=user_id))
        await db.commit()

    _run(_add)


def _png(color: str = "red") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 32), color=color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_staff_deletes_server_permanently_ca1():
    """CA 1: staff elimina un servidor -> se borran servidor, canales, categorías, roles, miembros,
    invitaciones, imágenes en S3 y se emite server.deleted en el outbox."""
    owner_id = f"auth0|{uuid.uuid4()}"
    member_id = f"auth0|{uuid.uuid4()}"
    server = _create_server(owner_id, "Comunidad Prohibida")
    server_id = server["id"]
    _add_member(server_id, member_id)

    owner_headers = {"x-user-id": owner_id}
    cat_res = client.post(f"/api/v1/servers/{server_id}/categories", json={"name": "Extra"}, headers=owner_headers)
    assert cat_res.status_code == 201
    chan_res = client.post(
        f"/api/v1/servers/{server_id}/channels",
        json={"name": "anuncios", "type": "text", "category_id": cat_res.json()["id"]},
        headers=owner_headers,
    )
    assert chan_res.status_code == 201
    role_res = client.post(f"/api/v1/servers/{server_id}/roles", json={"name": "Mod"}, headers=owner_headers)
    assert role_res.status_code == 201
    inv_res = client.post(f"/api/v1/servers/{server_id}/invites", json={}, headers=owner_headers)
    assert inv_res.status_code == 201

    res = client.request(
        "DELETE",
        f"/api/v1/admin/servers/{server_id}",
        json={"reason": "incumple términos de uso"},
        headers=STAFF,
    )
    assert res.status_code == 200, res.json()
    body = res.json()
    assert body["id"] == server_id
    assert body["name"] == "Comunidad Prohibida"
    assert body["owner_id"] == owner_id
    assert body["member_count"] == 2
    assert body["deleted_by"] == "auth0|staff"
    assert body["reason"] == "incumple términos de uso"

    # Ya no aparece en la lista del owner ni en el listado de staff
    assert not any(s["id"] == server_id for s in client.get("/api/v1/servers", headers=owner_headers).json())
    admin_list = client.get("/api/v1/admin/servers", headers=STAFF).json()
    assert not any(s["id"] == server_id for s in admin_list["items"])

    async def _check_db(db):
        sid = uuid.UUID(server_id)
        assert await db.scalar(select(Server).where(Server.id == sid)) is None
        assert list((await db.execute(select(Channel).where(Channel.server_id == sid))).scalars().all()) == []
        assert list((await db.execute(select(Category).where(Category.server_id == sid))).scalars().all()) == []
        assert list((await db.execute(select(Role).where(Role.server_id == sid))).scalars().all()) == []
        assert list((await db.execute(select(ServerMember).where(ServerMember.server_id == sid))).scalars().all()) == []
        assert list((await db.execute(select(ServerInvite).where(ServerInvite.server_id == sid))).scalars().all()) == []

        outbox_rows = (
            await db.execute(select(OutboxEvent).where(OutboxEvent.routing_key == "server.deleted"))
        ).scalars().all()
        events = [e for e in outbox_rows if e.payload.get("server_id") == server_id]
        assert len(events) == 1
        payload = events[0].payload
        assert payload["deleted_by"] == "auth0|staff"
        assert payload["reason"] == "incumple términos de uso"
        assert len(payload["channel_ids"]) == 3
        assert len(payload["voice_channel_ids"]) == 1
        assert set(payload["member_ids"]) == {owner_id, member_id}

    _run(_check_db)


def test_staff_can_delete_suspended_server_and_without_body():
    owner_id = f"auth0|{uuid.uuid4()}"
    server = _create_server(owner_id, "Suspendido Luego Borrado")
    server_id = server["id"]

    sus_res = client.post(
        f"/api/v1/admin/servers/{server_id}/suspension",
        json={"reason": "investigación"},
        headers=STAFF,
    )
    assert sus_res.status_code == 201

    del_res = client.delete(f"/api/v1/admin/servers/{server_id}", headers=STAFF)
    assert del_res.status_code == 200
    assert del_res.json()["id"] == server_id
    assert del_res.json()["reason"] is None


def test_staff_delete_server_cleans_storage_images():
    owner_id = f"auth0|{uuid.uuid4()}"
    with (
        patch("app.services.storage.upload_image", return_value="https://test.s3.amazonaws.com/server-icons/staff-del.webp"),
        patch("app.services.storage.delete_image") as mock_delete,
    ):
        files = {"icon": ("icon.png", _png("green"), "image/png")}
        create_res = client.post(
            "/api/v1/servers",
            data={"name": "Con Icono"},
            files=files,
            headers={"x-user-id": owner_id},
        )
        assert create_res.status_code == 201
        server_id = create_res.json()["id"]

        res = client.delete(f"/api/v1/admin/servers/{server_id}", headers=STAFF)
        assert res.status_code == 200
        mock_delete.assert_called_with("https://test.s3.amazonaws.com/server-icons/staff-del.webp")


def test_non_staff_cannot_delete_server_from_backoffice_ca2():
    """CA 2: usuario sin rol staff (incluso el dueño del servidor) no puede eliminar desde el endpoint de staff."""
    owner_id = f"auth0|{uuid.uuid4()}"
    server = _create_server(owner_id, "Protegido")
    server_id = server["id"]

    for headers in (
        {"x-user-id": owner_id, "x-user-role": "user"},
        {"x-user-id": owner_id},
        {"x-user-id": "auth0|other", "x-user-role": "admin"},
    ):
        res = client.request(
            "DELETE",
            f"/api/v1/admin/servers/{server_id}",
            json={"reason": "intento"},
            headers=headers,
        )
        assert res.status_code == 403
        assert res.json()["type"] == "https://discordia.app/problems/staff-only"

    # Sin identidad -> 401
    unauth = client.delete(f"/api/v1/admin/servers/{server_id}")
    assert unauth.status_code == 401

    # El servidor sigue intacto
    assert any(s["id"] == server_id for s in client.get("/api/v1/servers", headers={"x-user-id": owner_id}).json())


def test_staff_delete_nonexistent_server_returns_404():
    res = client.delete(f"/api/v1/admin/servers/{uuid.uuid4()}", headers=STAFF)
    assert res.status_code == 404


def test_staff_delete_blank_reason_returns_422():
    owner_id = f"auth0|{uuid.uuid4()}"
    server = _create_server(owner_id, "Validación Motivo")
    res = client.request(
        "DELETE",
        f"/api/v1/admin/servers/{server['id']}",
        json={"reason": "   "},
        headers=STAFF,
    )
    assert res.status_code == 422
