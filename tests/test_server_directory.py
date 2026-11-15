"""Ver listado de servidores de la plataforma (backoffice, solo staff): búsqueda, filtro de estado y paginado."""

import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

STAFF = {"x-user-id": "auth0|staff", "x-user-role": "staff"}


def create_server(name: str) -> dict:
    owner = f"auth0|{uuid.uuid4()}"
    response = client.post("/api/v1/servers", data={"name": name}, headers={"x-user-id": owner})
    assert response.status_code == 201, response.json()
    return response.json()


def list_servers(headers: dict = STAFF, **params):
    return client.get("/api/v1/admin/servers", params=params, headers=headers)


def unique(prefix: str) -> str:
    # La base de tests se comparte entre tests: cada uno busca por un nombre propio
    return f"{prefix} {uuid.uuid4().hex[:8]}"


def test_staff_searches_servers_by_name_and_sees_their_id():
    tag = unique("Directorio")
    first = create_server(f"{tag} uno")
    second = create_server(f"{tag} dos")
    create_server(unique("Otro"))

    response = list_servers(q=tag.upper())

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["total"] == 2
    assert {s["id"] for s in body["items"]} == {first["id"], second["id"]}
    # El más nuevo primero, con lo que el backoffice muestra
    item = body["items"][0]
    assert item["id"] == second["id"]
    assert item["member_count"] == 1  # el dueño
    assert item["is_suspended"] is False
    assert {"name", "owner_id", "created_at"} <= item.keys()


def test_two_servers_with_the_same_name_are_told_apart_by_id():
    name = unique("Repetido")
    a = create_server(name)
    b = create_server(name)

    items = list_servers(q=name).json()["items"]

    assert len(items) == 2
    assert {s["id"] for s in items} == {a["id"], b["id"]}


def test_search_by_exact_id():
    server = create_server(unique("PorId"))

    body = list_servers(q=server["id"]).json()

    assert body["total"] == 1
    assert body["items"][0]["id"] == server["id"]


def test_like_wildcards_are_literal():
    tag = unique("Comodin")
    create_server(f"{tag} 100%")
    create_server(f"{tag} 1000")

    body = list_servers(q=f"{tag} 100%").json()

    assert body["total"] == 1
    assert body["items"][0]["name"].endswith("100%")


def test_filter_by_suspension_state():
    tag = unique("Estado")
    active = create_server(f"{tag} activo")
    suspended = create_server(f"{tag} suspendido")
    response = client.post(
        f"/api/v1/admin/servers/{suspended['id']}/suspension", json={"reason": "denuncia"}, headers=STAFF
    )
    assert response.status_code == 201

    only_suspended = list_servers(q=tag, state="suspended").json()
    only_active = list_servers(q=tag, state="active").json()
    everything = list_servers(q=tag).json()

    assert [s["id"] for s in only_suspended["items"]] == [suspended["id"]]
    assert only_suspended["items"][0]["suspension_reason"] == "denuncia"
    assert [s["id"] for s in only_active["items"]] == [active["id"]]
    assert everything["total"] == 2


def test_pagination():
    tag = unique("Pagina")
    for i in range(3):
        create_server(f"{tag} {i}")

    first = list_servers(q=tag, page=1, page_size=2).json()
    second = list_servers(q=tag, page=2, page_size=2).json()

    assert first["total"] == 3
    assert len(first["items"]) == 2
    assert len(second["items"]) == 1
    assert {s["id"] for s in first["items"]}.isdisjoint({s["id"] for s in second["items"]})


def test_invalid_filters_are_422():
    assert list_servers(state="borrado").status_code == 422
    assert list_servers(page=0).status_code == 422
    assert list_servers(page_size=101).status_code == 422
    assert list_servers(q="x" * 101).status_code == 422


def test_only_staff_can_list_servers():
    assert list_servers(headers={"x-user-id": "auth0|user"}).status_code == 403
    assert list_servers(headers={"x-user-id": "auth0|user", "x-user-role": "user"}).status_code == 403
    assert list_servers(headers={}).status_code == 401
