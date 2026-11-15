import asyncio
import io
import uuid

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.models.server_ban import ServerBan
from app.models.server_member import ServerMember
from tests import db_utils

client = TestClient(app)


def headers_for(user_id: str) -> dict:
    return {"x-user-id": user_id}


def new_user() -> str:
    return f"auth0|{uuid.uuid4().hex}"


def create_server(owner_id: str, name: str = "Servidor") -> dict:
    response = client.post("/api/v1/servers", data={"name": name}, headers=headers_for(owner_id))
    assert response.status_code == 201, response.json()
    return response.json()


def add_member(server_id: str, user_id: str) -> None:
    async def _add():
        async with db_utils.TestingSessionLocal() as db:
            db.add(ServerMember(server_id=uuid.UUID(server_id), user_id=user_id))
            await db.commit()

    asyncio.run(_add())


def add_ban_row(server_id: str, user_id: str) -> None:
    """Fila de baneo sin tocar la membresía: el camino normal (POST /bans) borra al miembro."""

    async def _add():
        async with db_utils.TestingSessionLocal() as db:
            db.add(ServerBan(server_id=uuid.UUID(server_id), user_id=user_id))
            await db.commit()

    asyncio.run(_add())


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, format="PNG")
    return buffer.getvalue()


def get_mutual(viewer_id: str, other_id: str):
    return client.get(f"/api/v1/servers/mutual/{other_id}", headers=headers_for(viewer_id))


def test_returns_servers_shared_by_both_users():
    viewer, other = new_user(), new_user()
    first = create_server(viewer, "Primero")
    second = create_server(other, "Segundo")
    add_member(first["id"], other)
    add_member(second["id"], viewer)
    create_server(viewer, "Solo del que pide")
    create_server(other, "Solo del otro")

    response = get_mutual(viewer, other)

    assert response.status_code == 200, response.json()
    assert response.json() == [
        {"id": first["id"], "name": "Primero", "icon_url": None},
        {"id": second["id"], "name": "Segundo", "icon_url": None},
    ]


def test_response_includes_icon_url():
    viewer, other = new_user(), new_user()
    response = client.post(
        "/api/v1/servers",
        data={"name": "Con ícono"},
        files={"icon": ("icon.png", png_bytes(), "image/png")},
        headers=headers_for(viewer),
    )
    assert response.status_code == 201, response.json()
    server = response.json()
    assert server["icon_url"]
    add_member(server["id"], other)

    assert get_mutual(viewer, other).json() == [
        {"id": server["id"], "name": "Con ícono", "icon_url": server["icon_url"]}
    ]


def test_returns_empty_list_without_shared_servers():
    viewer, other = new_user(), new_user()
    create_server(viewer)
    create_server(other)

    response = get_mutual(viewer, other)

    assert response.status_code == 200
    assert response.json() == []


def test_returns_empty_list_for_unknown_user():
    viewer = new_user()
    create_server(viewer)

    response = get_mutual(viewer, new_user())

    assert response.status_code == 200
    assert response.json() == []


def test_excludes_server_after_banning_the_other_user():
    viewer, other = new_user(), new_user()
    banned_from = create_server(viewer, "Baneado")
    still_shared = create_server(viewer, "Sigue en común")
    add_member(banned_from["id"], other)
    add_member(still_shared["id"], other)

    ban = client.post(
        f"/api/v1/servers/{banned_from['id']}/bans",
        json={"user_id": other},
        headers=headers_for(viewer),
    )
    assert ban.status_code == 201, ban.json()

    expected = [{"id": still_shared["id"], "name": "Sigue en común", "icon_url": None}]
    assert get_mutual(viewer, other).json() == expected
    assert get_mutual(other, viewer).json() == expected


def test_excludes_server_when_other_user_has_ban_row_and_membership():
    viewer, other = new_user(), new_user()
    server = create_server(viewer)
    add_member(server["id"], other)
    add_ban_row(server["id"], other)

    assert get_mutual(viewer, other).json() == []


def test_excludes_server_when_viewer_has_ban_row_and_membership():
    viewer, other = new_user(), new_user()
    server = create_server(other)
    add_member(server["id"], viewer)
    add_ban_row(server["id"], viewer)

    assert get_mutual(viewer, other).json() == []


def test_ban_of_a_third_user_does_not_hide_the_server():
    viewer, other = new_user(), new_user()
    server = create_server(viewer)
    add_member(server["id"], other)
    add_ban_row(server["id"], new_user())

    assert [item["id"] for item in get_mutual(viewer, other).json()] == [server["id"]]


def test_accepts_url_encoded_auth0_id():
    viewer, other = new_user(), new_user()
    server = create_server(viewer)
    add_member(server["id"], other)

    response = client.get(f"/api/v1/servers/mutual/{other.replace('|', '%7C')}", headers=headers_for(viewer))

    assert response.status_code == 200, response.json()
    assert [item["id"] for item in response.json()] == [server["id"]]


def test_does_not_collide_with_server_routes():
    """Un usuario llamado "members" no cae en /servers/{server_id}/members."""
    response = get_mutual(new_user(), "members")

    assert response.status_code == 200
    assert response.json() == []


def test_requires_authenticated_user():
    response = client.get(f"/api/v1/servers/mutual/{new_user()}")

    assert response.status_code == 401
