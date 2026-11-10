import asyncio
import io
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

import tests.db_utils as db_utils
from app.main import app
from app.models.category import Category
from app.models.channel import Channel
from app.models.outbox_event import OutboxEvent
from app.models.role import Role
from app.models.server import Server
from app.models.server_member import ServerMember

client = TestClient(app)


def create_test_server(owner_id: str, name: str = "Test Server Deletion") -> str:
    payload = {"name": name}
    headers = {"x-user-id": owner_id}
    response = client.post("/api/v1/servers", data=payload, headers=headers)
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def add_member_to_server(server_id: str, user_id: str) -> str:
    async def _add():
        async with db_utils.TestingSessionLocal() as db:
            member = ServerMember(server_id=uuid.UUID(server_id), user_id=user_id)
            db.add(member)
            await db.commit()
            return str(member.id)

    return asyncio.run(_add())


def test_delete_server_success_ca1():
    """
    CA 1: Eliminación exitosa
    Dado que el owner de un servidor confirma su eliminación
    Cuando el sistema procesa la solicitud
    Entonces el servidor y todos sus canales, mensajes y roles se eliminan de forma permanente.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id, "Servidor a borrar")
    headers = {"x-user-id": owner_id}

    # Creamos un canal adicional y una categoría adicional
    cat_res = client.post(
        f"/api/v1/servers/{server_id}/categories", json={"name": "Categoría Extra"}, headers=headers
    )
    assert cat_res.status_code == 201
    category_id = cat_res.json()["id"]

    chan_res = client.post(
        f"/api/v1/servers/{server_id}/channels",
        json={"name": "canal-extra", "type": "text", "category_id": category_id},
        headers=headers,
    )
    assert chan_res.status_code == 201

    role_res = client.post(
        f"/api/v1/servers/{server_id}/roles", json={"name": "Rol Extra"}, headers=headers
    )
    assert role_res.status_code == 201

    # Eliminación por parte del owner
    del_res = client.delete(f"/api/v1/servers/{server_id}", headers=headers)
    assert del_res.status_code == 204

    # El servidor ya no aparece en GET /api/v1/servers
    list_res = client.get("/api/v1/servers", headers=headers)
    assert list_res.status_code == 200
    assert not any(s["id"] == server_id for s in list_res.json())

    # Verificamos que se borraron en cascada en la DB
    async def _check_db():
        async with db_utils.TestingSessionLocal() as db:
            s = await db.scalar(select(Server).where(Server.id == uuid.UUID(server_id)))
            assert s is None

            stmt_channels = select(Channel).where(Channel.server_id == uuid.UUID(server_id))
            channels = list((await db.execute(stmt_channels)).scalars().all())
            assert len(channels) == 0

            stmt_roles = select(Role).where(Role.server_id == uuid.UUID(server_id))
            roles = list((await db.execute(stmt_roles)).scalars().all())
            assert len(roles) == 0

            stmt_categories = select(Category).where(Category.server_id == uuid.UUID(server_id))
            categories = list((await db.execute(stmt_categories)).scalars().all())
            assert len(categories) == 0

            stmt_members = select(ServerMember).where(ServerMember.server_id == uuid.UUID(server_id))
            members = list((await db.execute(stmt_members)).scalars().all())
            assert len(members) == 0

            # Outbox event server.deleted generado
            events = list(
                (
                    await db.execute(
                        select(OutboxEvent).where(
                            OutboxEvent.routing_key == "server.deleted",
                            OutboxEvent.payload["server_id"].astext == server_id,
                        )
                    )
                ).scalars().all()
            )
            assert len(events) == 1
            assert events[0].status == "PENDING"
            assert "channel_ids" in events[0].payload
            assert len(events[0].payload["channel_ids"]) >= 3  # general, voz general, canal-extra

    asyncio.run(_check_db())


def test_non_owner_cannot_delete_server_ca2():
    """
    CA 2: Solo el owner puede eliminar
    Dado que un usuario que no es owner intenta eliminar el servidor
    Cuando accede a esa opción
    Entonces el sistema no se lo permite (403 Forbidden).
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id, "Servidor Privado")

    non_owner_id = str(uuid.uuid4())
    add_member_to_server(server_id, non_owner_id)

    # El no-owner intenta eliminar el servidor
    res = client.delete(f"/api/v1/servers/{server_id}", headers={"x-user-id": non_owner_id})
    assert res.status_code == 403
    assert "Only the server owner can delete this server" in res.json()["detail"]

    # Un usuario externo que ni siquiera es miembro tampoco puede
    stranger_id = str(uuid.uuid4())
    res_stranger = client.delete(f"/api/v1/servers/{server_id}", headers={"x-user-id": stranger_id})
    assert res_stranger.status_code == 403

    # El servidor sigue existiendo
    list_res = client.get("/api/v1/servers", headers={"x-user-id": owner_id})
    assert any(s["id"] == server_id for s in list_res.json())


def test_delete_non_existent_server_returns_404():
    random_id = str(uuid.uuid4())
    res = client.delete(f"/api/v1/servers/{random_id}", headers={"x-user-id": str(uuid.uuid4())})
    assert res.status_code == 404


def _png(color: str = "blue") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 32), color=color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_delete_server_deletes_icon_from_storage():
    owner_id = str(uuid.uuid4())
    headers = {"x-user-id": owner_id}

    with (
        patch("app.services.storage.upload_image", return_value="https://test.s3.amazonaws.com/server-icons/test.webp"),
        patch("app.services.storage.delete_image") as mock_delete,
    ):
        # Creamos servidor con ícono
        files = {"icon": ("icon.png", _png("red"), "image/png")}
        create_res = client.post("/api/v1/servers", data={"name": "Server Con Icono"}, files=files, headers=headers)
        assert create_res.status_code == 201
        server_id = create_res.json()["id"]

        del_res = client.delete(f"/api/v1/servers/{server_id}", headers=headers)
        assert del_res.status_code == 204
        mock_delete.assert_called_with("https://test.s3.amazonaws.com/server-icons/test.webp")
