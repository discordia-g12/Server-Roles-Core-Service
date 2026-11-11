"""Configuración general del servidor: nombre y descripción (PATCH /servers/{id}) y banner
(PUT / DELETE /servers/{id}/banner). Historia "Administrar configuración del servidor":

- CA1: con MANAGE_SERVER, ADMINISTRATOR o siendo el dueño, el cambio se guarda y se avisa con server.updated
  (Chat lo reenvía a los miembros por el inbox).
- CA2: sin esos permisos, 403 y no cambia nada.
- CA3: con datos inválidos, 422 (nombre) o 400 (imagen) y no se guarda nada.

S3 no se toca: el fixture fake_storage de conftest.py registra las subidas y los borrados.
"""

import asyncio
import io
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.core.permissions import Permission
from app.main import app
from app.models.outbox_event import OutboxEvent
from tests import db_utils
from tests.test_server_bans import add_member, add_member_with_role, create_role, headers_for

client = TestClient(app)


def _png(size: tuple[int, int] = (1600, 400), color: str = "blue") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="PNG")
    return buffer.getvalue()


def _create_server(owner_id: str, name: str = "Settings Server") -> dict:
    response = client.post("/api/v1/servers", data={"name": name}, headers=headers_for(owner_id))
    assert response.status_code == 201, response.json()
    return response.json()


def _patch(server_id: str, user_id: str, body: dict):
    return client.patch(f"/api/v1/servers/{server_id}", json=body, headers=headers_for(user_id))


def _put_banner(server_id: str, user_id: str, content: bytes | None = None):
    files = {"banner": ("banner.png", content if content is not None else _png(), "image/png")}
    return client.put(f"/api/v1/servers/{server_id}/banner", files=files, headers=headers_for(user_id))


def _listed(server_id: str, user_id: str) -> dict:
    servers = client.get("/api/v1/servers", headers=headers_for(user_id)).json()
    return next(s for s in servers if s["id"] == server_id)


def _server_updated_events(server_id: str) -> list[OutboxEvent]:
    async def _query():
        async with db_utils.TestingSessionLocal() as db:
            rows = await db.scalars(select(OutboxEvent).where(OutboxEvent.routing_key == "server.updated"))
            return [e for e in rows.all() if e.payload.get("server_id") == server_id]

    return asyncio.run(_query())


# --- CA1: nombre y descripción ---


def test_owner_renames_server_and_every_member_sees_it():
    owner = str(uuid.uuid4())
    server = _create_server(owner)
    member = str(uuid.uuid4())
    add_member(server["id"], member)

    response = _patch(server["id"], owner, {"name": "  Nuevo nombre  ", "description": "Un servidor de prueba"})

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["name"] == "Nuevo nombre"  # con trim
    assert body["description"] == "Un servidor de prueba"
    assert len(body["channels"]) == 2  # la respuesta es el servidor completo
    assert body["my_permissions"] is not None
    # Lo ve cualquier miembro, no solo quien lo cambió
    listed = _listed(server["id"], member)
    assert listed["name"] == "Nuevo nombre"
    assert listed["description"] == "Un servidor de prueba"


def test_rename_emits_one_server_updated_event_with_only_the_id():
    owner = str(uuid.uuid4())
    server = _create_server(owner)

    _patch(server["id"], owner, {"name": "Renombrado"})

    events = _server_updated_events(server["id"])
    assert len(events) == 1
    assert events[0].payload["server_id"] == server["id"]


def test_patch_only_changes_the_fields_sent():
    owner = str(uuid.uuid4())
    server = _create_server(owner, name="Original")
    _patch(server["id"], owner, {"description": "Primera"})

    response = _patch(server["id"], owner, {"name": "Otro"})

    assert response.json()["description"] == "Primera"
    assert response.json()["name"] == "Otro"


@pytest.mark.parametrize("description", ["", "   ", None])
def test_empty_description_clears_it(description):
    owner = str(uuid.uuid4())
    server = _create_server(owner)
    _patch(server["id"], owner, {"description": "Algo"})

    response = _patch(server["id"], owner, {"description": description})

    assert response.status_code == 200, response.json()
    assert response.json()["description"] is None


def test_patch_without_changes_does_not_emit_event():
    owner = str(uuid.uuid4())
    server = _create_server(owner, name="Igual")

    response = _patch(server["id"], owner, {"name": "Igual"})

    assert response.status_code == 200
    assert _server_updated_events(server["id"]) == []


@pytest.mark.parametrize("permission", [Permission.MANAGE_SERVER, Permission.ADMINISTRATOR])
def test_member_with_manage_permission_can_rename(permission):
    owner = str(uuid.uuid4())
    server = _create_server(owner)
    role_id = create_role(server["id"], owner, "Admins", permission)
    manager = add_member_with_role(server["id"], owner, role_id)

    response = _patch(server["id"], manager, {"name": "Cambiado por admin"})

    assert response.status_code == 200, response.json()
    assert _listed(server["id"], owner)["name"] == "Cambiado por admin"


# --- CA2: sin permisos ---


def test_member_without_permission_gets_403_and_nothing_changes(fake_storage):
    owner = str(uuid.uuid4())
    server = _create_server(owner, name="Intacto")
    member = str(uuid.uuid4())
    add_member(server["id"], member)

    patch = _patch(server["id"], member, {"name": "Hackeado"})
    put = _put_banner(server["id"], member)
    delete = client.delete(f"/api/v1/servers/{server['id']}/banner", headers=headers_for(member))

    assert patch.status_code == 403
    assert "MANAGE_SERVER" in patch.json()["detail"]
    assert put.status_code == 403
    assert delete.status_code == 403
    assert _listed(server["id"], owner)["name"] == "Intacto"
    assert fake_storage["uploaded"] == []
    assert _server_updated_events(server["id"]) == []


def test_role_without_manage_server_gets_403():
    owner = str(uuid.uuid4())
    server = _create_server(owner)
    role_id = create_role(server["id"], owner, "Mods", Permission.MANAGE_CHANNELS)
    moderator = add_member_with_role(server["id"], owner, role_id)

    assert _patch(server["id"], moderator, {"name": "No"}).status_code == 403


def test_non_member_gets_403():
    owner = str(uuid.uuid4())
    server = _create_server(owner)

    assert _patch(server["id"], str(uuid.uuid4()), {"name": "No"}).status_code == 403


def test_unknown_server_gets_404():
    assert _patch(str(uuid.uuid4()), str(uuid.uuid4()), {"name": "X"}).status_code == 404


def test_without_identity_gets_401():
    owner = str(uuid.uuid4())
    server = _create_server(owner)

    assert client.patch(f"/api/v1/servers/{server['id']}", json={"name": "X"}).status_code == 401


# --- CA3: datos inválidos ---


@pytest.mark.parametrize(
    "body",
    [
        {"name": ""},
        {"name": "    "},
        {"name": "a" * 101},
        {"name": "con\x00nulo"},
        {"name": None},
        {"description": "d" * 1001},
        {},
        {"name": "Ok", "owner_id": "otro"},
    ],
    ids=["empty", "blank", "too-long", "null-byte", "null", "long-description", "no-fields", "unknown-field"],
)
def test_invalid_data_returns_422_and_nothing_is_saved(body):
    owner = str(uuid.uuid4())
    server = _create_server(owner, name="Sin cambios")

    response = _patch(server["id"], owner, body)

    assert response.status_code == 422, response.json()
    assert response.json()["invalid_params"]
    listed = _listed(server["id"], owner)
    assert listed["name"] == "Sin cambios"
    assert listed["owner_id"] == owner
    assert _server_updated_events(server["id"]) == []


def test_name_of_100_chars_is_accepted():
    owner = str(uuid.uuid4())
    server = _create_server(owner)

    response = _patch(server["id"], owner, {"name": "a" * 100})

    assert response.status_code == 200


def test_db_failure_on_rename_keeps_the_old_name(monkeypatch):
    from app.repositories.server import ServerRepository

    owner = str(uuid.uuid4())
    server = _create_server(owner, name="Antes")

    async def broken_update(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(ServerRepository, "update_server", broken_update)
    with pytest.raises(RuntimeError):
        _patch(server["id"], owner, {"name": "Después"})
    monkeypatch.undo()

    assert _listed(server["id"], owner)["name"] == "Antes"


# --- Banner ---


def test_owner_sets_banner_as_16_9_webp(fake_storage):
    owner = str(uuid.uuid4())
    server = _create_server(owner)
    member = str(uuid.uuid4())
    add_member(server["id"], member)

    response = _put_banner(server["id"], owner)

    assert response.status_code == 200, response.json()
    upload = fake_storage["uploaded"][-1]
    assert upload["prefix"] == "server-icons/banners"
    assert response.json()["banner_url"] == upload["url"]
    with Image.open(io.BytesIO(upload["contents"])) as image:
        assert image.format == "WEBP"
        assert image.size == (960, 540)
    # El ícono no se toca
    assert response.json()["icon_url"] is None
    assert _listed(server["id"], member)["banner_url"] == upload["url"]
    assert len(_server_updated_events(server["id"])) == 1


def test_replacing_banner_deletes_the_previous_one(fake_storage):
    owner = str(uuid.uuid4())
    server = _create_server(owner)
    first = _put_banner(server["id"], owner).json()["banner_url"]

    second = _put_banner(server["id"], owner, _png(color="red")).json()["banner_url"]

    assert second != first
    assert fake_storage["deleted"] == [first]


def test_member_with_manage_server_can_set_banner():
    owner = str(uuid.uuid4())
    server = _create_server(owner)
    role_id = create_role(server["id"], owner, "Admins", Permission.MANAGE_SERVER)
    manager = add_member_with_role(server["id"], owner, role_id)

    assert _put_banner(server["id"], manager).status_code == 200


@pytest.mark.parametrize(
    ("content", "detail"),
    [
        (b"not an image", "Use JPEG, PNG or WebP"),
        (b"", "empty"),
        (b"x" * (5 * 1024 * 1024 + 1), "Limit 5MB"),
    ],
    ids=["not-an-image", "empty", "too-big"],
)
def test_invalid_banner_returns_400_and_nothing_is_saved(fake_storage, content, detail):
    owner = str(uuid.uuid4())
    server = _create_server(owner)

    response = _put_banner(server["id"], owner, content)

    assert response.status_code == 400
    assert detail in response.json()["detail"]
    assert fake_storage["uploaded"] == []
    assert _listed(server["id"], owner)["banner_url"] is None
    assert _server_updated_events(server["id"]) == []


def test_banner_db_failure_deletes_the_uploaded_file_and_keeps_the_old_one(fake_storage, monkeypatch):
    from app.repositories.server import ServerRepository

    owner = str(uuid.uuid4())
    server = _create_server(owner)
    old_url = _put_banner(server["id"], owner).json()["banner_url"]

    async def broken_set_banner(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(ServerRepository, "set_banner", broken_set_banner)
    with pytest.raises(RuntimeError):
        _put_banner(server["id"], owner, _png(color="green"))
    monkeypatch.undo()

    new_url = fake_storage["uploaded"][-1]["url"]
    assert fake_storage["deleted"] == [new_url]
    assert _listed(server["id"], owner)["banner_url"] == old_url


def test_remove_banner_clears_it_and_deletes_the_file(fake_storage):
    owner = str(uuid.uuid4())
    server = _create_server(owner)
    url = _put_banner(server["id"], owner).json()["banner_url"]

    response = client.delete(f"/api/v1/servers/{server['id']}/banner", headers=headers_for(owner))

    assert response.status_code == 200, response.json()
    assert response.json()["banner_url"] is None
    assert fake_storage["deleted"] == [url]
    assert len(_server_updated_events(server["id"])) == 2


def test_remove_banner_without_banner_is_a_no_op(fake_storage):
    owner = str(uuid.uuid4())
    server = _create_server(owner)

    response = client.delete(f"/api/v1/servers/{server['id']}/banner", headers=headers_for(owner))

    assert response.status_code == 200
    assert fake_storage["deleted"] == []
    assert _server_updated_events(server["id"]) == []


def test_deleting_the_server_also_deletes_its_banner(fake_storage):
    owner = str(uuid.uuid4())
    server = _create_server(owner)
    url = _put_banner(server["id"], owner).json()["banner_url"]

    response = client.delete(f"/api/v1/servers/{server['id']}", headers=headers_for(owner))

    assert response.status_code == 204
    assert url in fake_storage["deleted"]


# --- Interno: a quién avisar ---


def test_internal_member_ids_lists_every_member():
    owner = str(uuid.uuid4())
    server = _create_server(owner)
    member = str(uuid.uuid4())
    add_member(server["id"], member)

    response = client.get(f"/internal/servers/{server['id']}/member-ids")

    assert response.status_code == 200
    assert response.json()["server_id"] == server["id"]
    assert sorted(response.json()["user_ids"]) == sorted([owner, member])


def test_internal_member_ids_of_unknown_server_is_404():
    assert client.get(f"/internal/servers/{uuid.uuid4()}/member-ids").status_code == 404
