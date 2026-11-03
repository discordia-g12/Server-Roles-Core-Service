import asyncio
import uuid

from fastapi.testclient import TestClient

from app.core.permissions import Permission
from app.main import app
from app.models.server_member import ServerMember
from tests import db_utils

client = TestClient(app)


def create_test_server(owner_id: str) -> str:
    payload = {"name": "Test Server Hierarchy"}
    headers = {"x-user-id": owner_id}
    response = client.post("/api/v1/servers", data=payload, headers=headers)
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def create_test_role(server_id: str, owner_id: str, name: str) -> str:
    payload = {"name": name}
    headers = {"x-user-id": owner_id}
    response = client.post(f"/api/v1/servers/{server_id}/roles", json=payload, headers=headers)
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def create_test_member(server_id: str, user_id: str) -> str:
    async def _create():
        async with db_utils.TestingSessionLocal() as db:
            member = ServerMember(server_id=uuid.UUID(server_id), user_id=user_id)
            db.add(member)
            await db.commit()
            return str(member.id)

    return asyncio.run(_create())


def assign_role(server_id: str, role_id: str, owner_id: str, target_user_id: str):
    return client.put(
        f"/api/v1/servers/{server_id}/roles/{role_id}/members/{target_user_id}",
        headers={"x-user-id": owner_id},
    )


def grant_manage_roles(server_id: str, role_id: str, owner_id: str):
    perm = Permission.MANAGE_ROLES.value | Permission.VIEW_CHANNELS.value
    return client.patch(
        f"/api/v1/servers/{server_id}/roles/{role_id}/permissions",
        json={"new_permissions_bitmask": perm},
        headers={"x-user-id": owner_id},
    )


def get_roles(server_id: str, user_id: str):
    return client.get(f"/api/v1/servers/{server_id}/roles", headers={"x-user-id": user_id})


# ============================================================================
# CA 1: Reordenamiento exitoso
# ============================================================================


def test_reorder_roles_owner_success_persisted():
    """
    CA 1: Reordenamiento exitoso por el dueño
    Dado que un usuario con permisos (Owner) cambia la posición de un rol dentro de la jerarquía
    Cuando confirma el cambio
    Entonces el nuevo orden se aplica y se persiste en el servidor.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)

    role_mod = create_test_role(server_id, owner_id, "Moderator")  # pos 1
    role_vip = create_test_role(server_id, owner_id, "VIP")  # pos 2

    roles_before = get_roles(server_id, owner_id).json()
    everyone_id = roles_before[0]["id"]
    assert [r["id"] for r in roles_before] == [everyone_id, role_mod, role_vip]

    # Reordenamos invirtiendo Moderator y VIP
    new_order = [everyone_id, role_vip, role_mod]
    response = client.put(
        f"/api/v1/servers/{server_id}/roles/order",
        json={"role_ids": new_order},
        headers={"x-user-id": owner_id},
    )

    assert response.status_code == 200
    data = response.json()
    assert [r["id"] for r in data] == new_order
    assert [r["position"] for r in data] == [0, 1, 2]

    # Verificamos persistencia con get_roles
    roles_after = get_roles(server_id, owner_id).json()
    assert [r["id"] for r in roles_after] == new_order
    assert [r["position"] for r in roles_after] == [0, 1, 2]


def test_reorder_roles_member_with_manage_roles_can_reorder_lower_roles():
    """
    CA 1: Miembro con MANAGE_ROLES reordena roles inferiores al propio
    Un administrador con rol superior puede reordenar los roles que están por debajo del suyo.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)

    role_a = create_test_role(server_id, owner_id, "Role A")  # pos 1
    role_b = create_test_role(server_id, owner_id, "Role B")  # pos 2
    role_admin = create_test_role(server_id, owner_id, "Admin Role")  # pos 3
    grant_manage_roles(server_id, role_admin, owner_id)

    member_id = str(uuid.uuid4())
    create_test_member(server_id, member_id)
    assign_role(server_id, role_admin, owner_id, member_id)

    roles_before = get_roles(server_id, owner_id).json()
    everyone_id = roles_before[0]["id"]

    # El admin reordena Role A y Role B (ambos inferiores a Admin Role en pos 3)
    new_order = [everyone_id, role_b, role_a, role_admin]
    response = client.put(
        f"/api/v1/servers/{server_id}/roles/order",
        json={"role_ids": new_order},
        headers={"x-user-id": member_id},
    )

    assert response.status_code == 200
    data = response.json()
    assert [r["id"] for r in data] == new_order
    assert [r["position"] for r in data] == [0, 1, 2, 3]


# ============================================================================
# CA 2: Restricción sobre roles superiores
# ============================================================================


def test_reorder_roles_cannot_move_role_above_own_highest_role():
    """
    CA 2: Restricción sobre roles superiores
    Dado que un usuario con permisos intenta reordenar un rol que está por encima del propio
    en la jerarquía
    Cuando lo intenta
    Entonces el sistema no se lo permite (403 Forbidden).
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)

    role_mod = create_test_role(server_id, owner_id, "Moderator")  # pos 1
    role_admin = create_test_role(server_id, owner_id, "Admin")  # pos 2
    role_coowner = create_test_role(server_id, owner_id, "Co-Owner")  # pos 3
    grant_manage_roles(server_id, role_admin, owner_id)

    # Miembro tiene rol Admin (pos 2). Co-Owner (pos 3) está por encima.
    member_id = str(uuid.uuid4())
    create_test_member(server_id, member_id)
    assign_role(server_id, role_admin, owner_id, member_id)

    roles_before = get_roles(server_id, owner_id).json()
    everyone_id = roles_before[0]["id"]

    # Intento 1: Intercambiar Co-Owner (pos 3) con Moderator (pos 1) -> Toca un rol superior
    attempt_move_higher_role = [everyone_id, role_coowner, role_admin, role_mod]
    response = client.put(
        f"/api/v1/servers/{server_id}/roles/order",
        json={"role_ids": attempt_move_higher_role},
        headers={"x-user-id": member_id},
    )

    assert response.status_code == 403
    assert "detail" in response.json()


def test_reorder_roles_cannot_elevate_role_above_or_equal_to_own_highest_role():
    """
    CA 2: No se permite mover un rol inferior al nivel o por encima del rol más alto del usuario.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)

    role_helper = create_test_role(server_id, owner_id, "Helper")  # pos 1
    role_admin = create_test_role(server_id, owner_id, "Admin")  # pos 2
    grant_manage_roles(server_id, role_admin, owner_id)

    member_id = str(uuid.uuid4())
    create_test_member(server_id, member_id)
    assign_role(server_id, role_admin, owner_id, member_id)

    roles_before = get_roles(server_id, owner_id).json()
    everyone_id = roles_before[0]["id"]

    # Intenta subir Helper por encima de su propio Admin
    attempt_elevate = [everyone_id, role_admin, role_helper]
    response = client.put(
        f"/api/v1/servers/{server_id}/roles/order",
        json={"role_ids": attempt_elevate},
        headers={"x-user-id": member_id},
    )

    assert response.status_code == 403


def test_reorder_roles_cannot_move_own_highest_role():
    """
    CA 2: Un usuario no puede alterar la posición de su propio rol más alto en la jerarquía.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)

    role_admin = create_test_role(server_id, owner_id, "Admin")  # pos 1
    role_other = create_test_role(server_id, owner_id, "Other")  # pos 2
    grant_manage_roles(server_id, role_admin, owner_id)

    member_id = str(uuid.uuid4())
    create_test_member(server_id, member_id)
    assign_role(server_id, role_admin, owner_id, member_id)

    roles_before = get_roles(server_id, owner_id).json()
    everyone_id = roles_before[0]["id"]

    # Intenta mover su propio Admin a posición 2
    attempt = [everyone_id, role_other, role_admin]
    response = client.put(
        f"/api/v1/servers/{server_id}/roles/order",
        json={"role_ids": attempt},
        headers={"x-user-id": member_id},
    )

    assert response.status_code == 403


# ============================================================================
# Permisos y Validaciones
# ============================================================================


def test_reorder_roles_without_manage_permission_fails():
    """
    CA 2: Usuario sin permisos de administración intenta reordenar roles -> 403 Forbidden
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)

    role_mod = create_test_role(server_id, owner_id, "Moderator")
    role_vip = create_test_role(server_id, owner_id, "VIP")

    member_id = str(uuid.uuid4())
    create_test_member(server_id, member_id)
    assign_role(server_id, role_vip, owner_id, member_id)

    roles = get_roles(server_id, owner_id).json()
    everyone_id = roles[0]["id"]

    response = client.put(
        f"/api/v1/servers/{server_id}/roles/order",
        json={"role_ids": [everyone_id, role_vip, role_mod]},
        headers={"x-user-id": member_id},
    )

    assert response.status_code == 403


def test_reorder_roles_non_member_fails():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_mod = create_test_role(server_id, owner_id, "Moderator")

    roles = get_roles(server_id, owner_id).json()
    everyone_id = roles[0]["id"]

    random_user_id = str(uuid.uuid4())
    response = client.put(
        f"/api/v1/servers/{server_id}/roles/order",
        json={"role_ids": [everyone_id, role_mod]},
        headers={"x-user-id": random_user_id},
    )

    assert response.status_code == 403


def test_reorder_roles_fails_when_role_missing():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_mod = create_test_role(server_id, owner_id, "Moderator")
    create_test_role(server_id, owner_id, "VIP")

    roles = get_roles(server_id, owner_id).json()
    everyone_id = roles[0]["id"]

    # Falta VIP en la lista
    response = client.put(
        f"/api/v1/servers/{server_id}/roles/order",
        json={"role_ids": [everyone_id, role_mod]},
        headers={"x-user-id": owner_id},
    )

    assert response.status_code == 400


def test_reorder_roles_fails_with_duplicate_role():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    role_mod = create_test_role(server_id, owner_id, "Moderator")

    roles = get_roles(server_id, owner_id).json()
    everyone_id = roles[0]["id"]

    response = client.put(
        f"/api/v1/servers/{server_id}/roles/order",
        json={"role_ids": [everyone_id, role_mod, role_mod]},
        headers={"x-user-id": owner_id},
    )

    assert response.status_code == 400


def test_reorder_roles_fails_with_foreign_role():
    owner_id = str(uuid.uuid4())
    server_id1 = create_test_server(owner_id)
    server_id2 = create_test_server(owner_id)

    role_s1 = create_test_role(server_id1, owner_id, "Role S1")
    role_s2 = create_test_role(server_id2, owner_id, "Role S2")

    roles1 = get_roles(server_id1, owner_id).json()
    everyone_id1 = roles1[0]["id"]

    response = client.put(
        f"/api/v1/servers/{server_id1}/roles/order",
        json={"role_ids": [everyone_id1, role_s1, role_s2]},
        headers={"x-user-id": owner_id},
    )

    assert response.status_code == 400
