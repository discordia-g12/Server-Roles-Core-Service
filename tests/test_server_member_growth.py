import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.core.permissions import Permission
from app.main import app
from app.models.role import Role
from app.models.role_assignment import RoleAssignment
from app.models.server_member import ServerMember
from app.models.server_member_event import ServerMemberEvent
from tests import db_utils

client = TestClient(app)


def _create_server(owner_id: str) -> str:
    headers = {"x-user-id": owner_id}
    res = client.post("/api/v1/servers", data={"name": "Growth Test Server"}, headers=headers)
    assert res.status_code == 201
    return res.json()["id"]


def _assign_role_with_permissions(server_id: str, user_id: str, permissions: int):
    async def _add_member_and_role():
        async with db_utils.TestingSessionLocal() as db:
            role = Role(
                server_id=uuid.UUID(server_id),
                name="Manager",
                position=1,
                permissions_bitmask=permissions,
                is_default=False,
            )
            db.add(role)
            await db.flush()
            member = ServerMember(server_id=uuid.UUID(server_id), user_id=user_id)
            db.add(member)
            await db.flush()
            db.add(RoleAssignment(server_member_id=member.id, role_id=role.id))
            await db.commit()

    asyncio.run(_add_member_and_role())


def test_member_growth_ca1_evolution_chart():
    """CA 1: Gráfico de evolución día a día con altas y bajas."""
    owner_id = str(uuid.uuid4())
    server_id = _create_server(owner_id)

    today = datetime.now(UTC).date()
    d1 = today - timedelta(days=4)
    d2 = today - timedelta(days=3)
    d3 = today - timedelta(days=2)
    d4 = today - timedelta(days=1)
    d5 = today

    async def _setup_events():
        async with db_utils.TestingSessionLocal() as db:
            from sqlalchemy import update
            # Move owner join to d1
            await db.execute(
                update(ServerMemberEvent)
                .where(
                    ServerMemberEvent.server_id == uuid.UUID(server_id),
                    ServerMemberEvent.user_id == owner_id,
                )
                .values(created_at=datetime.combine(d1, datetime.min.time()))
            )
            # Add member on d2
            u2 = str(uuid.uuid4())
            db.add(ServerMemberEvent(
                server_id=uuid.UUID(server_id),
                user_id=u2,
                event_type="join",
                created_at=datetime.combine(d2, datetime.min.time()),
            ))
            # Add another member on d3
            u3 = str(uuid.uuid4())
            db.add(ServerMemberEvent(
                server_id=uuid.UUID(server_id),
                user_id=u3,
                event_type="join",
                created_at=datetime.combine(d3, datetime.min.time()),
            ))
            # u2 leaves on d4
            db.add(ServerMemberEvent(
                server_id=uuid.UUID(server_id),
                user_id=u2,
                event_type="leave",
                created_at=datetime.combine(d4, datetime.min.time()),
            ))
            await db.commit()

    asyncio.run(_setup_events())

    headers = {"x-user-id": owner_id}
    res = client.get(
        f"/api/v1/servers/{server_id}/metrics/member-growth",
        params={"start_date": d1.isoformat(), "end_date": d5.isoformat()},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["server_id"] == server_id
    assert body["period"]["days"] == 5
    data = body["data"]
    assert len(data) == 5

    # Day 1: owner only -> count 1
    assert data[0]["date"] == d1.isoformat()
    assert data[0]["member_count"] == 1

    # Day 2: u2 joined -> count 2
    assert data[1]["date"] == d2.isoformat()
    assert data[1]["member_count"] == 2
    assert data[1]["joined"] == 1
    assert data[1]["left"] == 0

    # Day 3: u3 joined -> count 3
    assert data[2]["date"] == d3.isoformat()
    assert data[2]["member_count"] == 3
    assert data[2]["joined"] == 1
    assert data[2]["left"] == 0

    # Day 4: u2 left -> count 2
    assert data[3]["date"] == d4.isoformat()
    assert data[3]["member_count"] == 2
    assert data[3]["joined"] == 0
    assert data[3]["left"] == 1

    # Day 5: no changes -> count 2
    assert data[4]["date"] == d5.isoformat()
    assert data[4]["member_count"] == 2
    assert data[4]["joined"] == 0
    assert data[4]["left"] == 0


def test_member_growth_days_parameter():
    """Consulta con parámetro days (ej. 7 días)."""
    owner_id = str(uuid.uuid4())
    server_id = _create_server(owner_id)

    headers = {"x-user-id": owner_id}
    res = client.get(
        f"/api/v1/servers/{server_id}/metrics/member-growth",
        params={"days": 7},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["period"]["days"] == 7
    assert len(body["data"]) == 7


def test_member_growth_permissions():
    """Solo owner o miembros con MANAGE_SERVER o ADMINISTRATOR pueden consultar."""
    owner_id = str(uuid.uuid4())
    server_id = _create_server(owner_id)

    # 1. Owner -> 200
    res_owner = client.get(
        f"/api/v1/servers/{server_id}/metrics/member-growth",
        headers={"x-user-id": owner_id},
    )
    assert res_owner.status_code == 200

    # 2. Member with MANAGE_SERVER -> 200
    manager_id = str(uuid.uuid4())
    _assign_role_with_permissions(server_id, manager_id, int(Permission.MANAGE_SERVER))
    res_manager = client.get(
        f"/api/v1/servers/{server_id}/metrics/member-growth",
        headers={"x-user-id": manager_id},
    )
    assert res_manager.status_code == 200

    # 3. Regular member without permissions -> 403
    regular_id = str(uuid.uuid4())

    async def _add_regular():
        async with db_utils.TestingSessionLocal() as db:
            db.add(ServerMember(server_id=uuid.UUID(server_id), user_id=regular_id))
            await db.commit()

    asyncio.run(_add_regular())

    res_reg = client.get(
        f"/api/v1/servers/{server_id}/metrics/member-growth",
        headers={"x-user-id": regular_id},
    )
    assert res_reg.status_code == 403

    # 4. Non-member -> 403
    stranger_id = str(uuid.uuid4())
    res_stranger = client.get(
        f"/api/v1/servers/{server_id}/metrics/member-growth",
        headers={"x-user-id": stranger_id},
    )
    assert res_stranger.status_code == 403

    # 5. Non-existent server -> 404
    res_404 = client.get(
        f"/api/v1/servers/{uuid.uuid4()}/metrics/member-growth",
        headers={"x-user-id": owner_id},
    )
    assert res_404.status_code == 404


def test_member_growth_invalid_dates():
    """start_date posterior a end_date devuelve 422."""
    owner_id = str(uuid.uuid4())
    server_id = _create_server(owner_id)

    res = client.get(
        f"/api/v1/servers/{server_id}/metrics/member-growth",
        params={"start_date": "2026-11-10", "end_date": "2026-11-01"},
        headers={"x-user-id": owner_id},
    )
    assert res.status_code == 422


def test_member_growth_live_lifecycle():
    """Flujo real con la API: creación, unión por invitación y abandono."""
    owner_id = str(uuid.uuid4())
    server_id = _create_server(owner_id)

    # 1. Crear invitación
    invite_res = client.post(
        f"/api/v1/servers/{server_id}/invites",
        json={"max_uses": 10},
        headers={"x-user-id": owner_id},
    )
    assert invite_res.status_code == 201
    code = invite_res.json()["code"]

    # 2. Usuario 2 se une por invitación
    u2_id = str(uuid.uuid4())
    join_res = client.post(f"/api/v1/invites/{code}/join", headers={"x-user-id": u2_id})
    assert join_res.status_code == 200

    # 3. Usuario 2 abandona el servidor
    leave_res = client.delete(f"/api/v1/servers/{server_id}/leave", headers={"x-user-id": u2_id})
    assert leave_res.status_code == 204

    # 4. Consultar crecimiento de miembros hoy
    res = client.get(
        f"/api/v1/servers/{server_id}/metrics/member-growth",
        params={"days": 1},
        headers={"x-user-id": owner_id},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["current_member_count"] == 1
    assert len(body["data"]) == 1
    today_data = body["data"][0]
    assert today_data["member_count"] == 1
    # Se unieron el owner y u2
    assert today_data["joined"] == 2
    # u2 abandonó
    assert today_data["left"] == 1

