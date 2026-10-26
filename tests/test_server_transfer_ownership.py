import asyncio
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.models.server_member import ServerMember
from tests import db_utils

client = TestClient(app)


def create_test_server(owner_id: str) -> str:
    """Helper para crear un servidor de pruebas."""
    payload = {"name": "Test Server Ownership Transfer"}
    headers = {"x-user-id": owner_id}
    response = client.post("/api/v1/servers", data=payload, headers=headers)
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def add_member_to_server(server_id: str, user_id: str) -> str:
    """Inserta directamente un ServerMember en la BD."""

    async def _add():
        async with db_utils.TestingSessionLocal() as db:
            member = ServerMember(server_id=uuid.UUID(server_id), user_id=user_id)
            db.add(member)
            await db.commit()
            return str(member.id)

    return asyncio.run(_add())


def test_transfer_ownership_success_ca1():
    """
    CA 1: Transferencia exitosa
    Dado que el owner selecciona a otro miembro del servidor y confirma la transferencia
    Cuando el otro miembro acepta
    Entonces ese miembro pasa a ser el nuevo owner y el anterior queda como miembro regular.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)

    member_id = str(uuid.uuid4())
    add_member_to_server(server_id, member_id)

    headers_owner = {"x-user-id": owner_id}
    response_init = client.post(
        f"/api/v1/servers/{server_id}/transfers",
        json={"target_user_id": member_id},
        headers=headers_owner,
    )
    assert response_init.status_code == 201
    transfer_data = response_init.json()
    assert transfer_data["status"] == "PENDING"
    assert transfer_data["target_user_id"] == member_id
    assert transfer_data["sender_id"] == owner_id
    transfer_id = transfer_data["id"]

    headers_member = {"x-user-id": member_id}
    response_accept = client.post(
        f"/api/v1/servers/{server_id}/transfers/{transfer_id}/accept",
        headers=headers_member,
    )
    assert response_accept.status_code == 200
    assert response_accept.json()["status"] == "ACCEPTED"

    response_servers_member = client.get("/api/v1/servers", headers=headers_member)
    assert response_servers_member.status_code == 200
    server_info = next(s for s in response_servers_member.json() if s["id"] == server_id)
    assert server_info["owner_id"] == member_id

    response_leave = client.delete(f"/api/v1/servers/{server_id}/leave", headers=headers_owner)
    assert response_leave.status_code == 204


def test_transfer_ownership_to_non_member_fails_ca2():
    """
    CA 2: Transferencia a no miembro
    Dado que el owner intenta transferir la propiedad a alguien que no es miembro del servidor
    Cuando lo intenta
    Entonces el sistema no lo permite (400 Bad Request).
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)

    non_member_id = str(uuid.uuid4())
    headers_owner = {"x-user-id": owner_id}

    response = client.post(
        f"/api/v1/servers/{server_id}/transfers",
        json={"target_user_id": non_member_id},
        headers=headers_owner,
    )
    assert response.status_code == 400
    assert "Target user is not a member of this server" in response.json()["detail"]

    response_servers = client.get("/api/v1/servers", headers=headers_owner)
    server_info = next(s for s in response_servers.json() if s["id"] == server_id)
    assert server_info["owner_id"] == owner_id


def test_transfer_ownership_rejected_ca3():
    """
    CA 3: Transferencia rechazada
    Dado que el owner inicia una transferencia y el destinatario la rechaza
    Cuando esto ocurre
    Entonces la propiedad no cambia y el owner original la conserva.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)

    member_id = str(uuid.uuid4())
    add_member_to_server(server_id, member_id)

    headers_owner = {"x-user-id": owner_id}
    response_init = client.post(
        f"/api/v1/servers/{server_id}/transfers",
        json={"target_user_id": member_id},
        headers=headers_owner,
    )
    assert response_init.status_code == 201
    transfer_id = response_init.json()["id"]

    headers_member = {"x-user-id": member_id}
    response_reject = client.post(
        f"/api/v1/servers/{server_id}/transfers/{transfer_id}/reject",
        headers=headers_member,
    )
    assert response_reject.status_code == 200
    assert response_reject.json()["status"] == "REJECTED"

    response_servers = client.get("/api/v1/servers", headers=headers_owner)
    server_info = next(s for s in response_servers.json() if s["id"] == server_id)
    assert server_info["owner_id"] == owner_id


def test_transfer_ownership_non_owner_forbidden():
    """Solo el owner puede iniciar una transferencia."""
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)

    member_id = str(uuid.uuid4())
    add_member_to_server(server_id, member_id)

    other_user_id = str(uuid.uuid4())
    add_member_to_server(server_id, other_user_id)

    headers_member = {"x-user-id": member_id}
    response = client.post(
        f"/api/v1/servers/{server_id}/transfers",
        json={"target_user_id": other_user_id},
        headers=headers_member,
    )
    assert response.status_code == 403


def test_transfer_ownership_cannot_transfer_to_self():
    """El owner no puede transferirse la propiedad a sí mismo."""
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)

    headers_owner = {"x-user-id": owner_id}
    response = client.post(
        f"/api/v1/servers/{server_id}/transfers",
        json={"target_user_id": owner_id},
        headers=headers_owner,
    )
    assert response.status_code == 400
    assert "Cannot transfer ownership to yourself" in response.json()["detail"]


def test_transfer_ownership_only_recipient_can_accept_or_reject():
    """Un usuario que no es el destinatario no puede aceptar ni rechazar."""
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)

    member_id = str(uuid.uuid4())
    add_member_to_server(server_id, member_id)

    impostor_id = str(uuid.uuid4())
    add_member_to_server(server_id, impostor_id)

    headers_owner = {"x-user-id": owner_id}
    response_init = client.post(
        f"/api/v1/servers/{server_id}/transfers",
        json={"target_user_id": member_id},
        headers=headers_owner,
    )
    transfer_id = response_init.json()["id"]

    headers_impostor = {"x-user-id": impostor_id}
    response_accept = client.post(
        f"/api/v1/servers/{server_id}/transfers/{transfer_id}/accept",
        headers=headers_impostor,
    )
    assert response_accept.status_code == 403
