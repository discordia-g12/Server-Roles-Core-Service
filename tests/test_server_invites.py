import uuid
from datetime import UTC
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

def create_test_server(owner_id: str) -> str:
    """Helper to quickly create a server before tests."""
    payload = {"name": "Invite Test Server"}
    headers = {"x-user-id": owner_id}
    response = client.post("/api/v1/servers", data=payload, headers=headers)
    return response.json()["id"]


def test_create_invite_success():
    """
    AC 1: Invite generated
    Given that a user with invite permissions is in a server
    When they generate an invite
    Then the system creates a unique and configurable link.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    
    payload = {"max_uses": 5, "expires_in_seconds": 3600}
    headers = {"x-user-id": owner_id}
    
    response = client.post(f"/api/v1/servers/{server_id}/invites", json=payload, headers=headers)
    
    assert response.status_code == 201
    data = response.json()
    assert "code" in data
    assert len(data["code"]) > 0
    assert data["max_uses"] == 5
    assert data["uses"] == 0
    assert data["is_revoked"] is False
    assert data["expires_at"] is not None


def test_create_invite_without_permissions():
    """
    Implicit permission validation in AC 1.
    A user without the proper role/permission cannot generate invites.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    
    random_user_id = str(uuid.uuid4())
    headers_random = {"x-user-id": random_user_id}
    payload = {"max_uses": 1, "expires_in_seconds": 3600}
    
    response = client.post(f"/api/v1/servers/{server_id}/invites", json=payload, headers=headers_random)
    
    assert response.status_code == 403
    assert "Insufficient permissions." in response.json()["detail"]


def test_revoke_invite_success():
    """
    AC 4: Revoke invite
    Given that a user with permissions views an active server invite
    When they manually revoke it
    Then the link stops working immediately.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    headers = {"x-user-id": owner_id}
    
    res_create = client.post(
        f"/api/v1/servers/{server_id}/invites", 
        json={"max_uses": 10}, 
        headers=headers
    )
    code = res_create.json()["code"]
    

    res_revoke = client.delete(f"/api/v1/servers/{server_id}/invites/{code}", headers=headers)
    assert res_revoke.status_code == 204

    # check that you cannot join
    random_user_id = str(uuid.uuid4())
    res_join = client.post(f"/api/v1/invites/{code}/join", headers={"x-user-id": random_user_id})
    assert res_join.status_code == 400
    assert "no longer valid" in res_join.json()["detail"]



@pytest.mark.anyio
async def test_invite_max_uses_reached(db_session):
    """
    AC 2: Invite with usage limit reached.
    Since invite usage is managed by an internal service/function,
    we test the service logic directly (Integration Test).
    """
    from app.services.invite import InviteService
        
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    
    from app.repositories.invite import InviteRepository
    service = InviteService(InviteRepository())
    
    invite = await service.create_invite(
        db_session, uuid.UUID(server_id), owner_id, max_uses=1, expires_in_seconds=3600
    )

    used_invite = await service.validate_and_use_invite(db_session, invite.code)
    assert used_invite.uses == 1
    
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await service.validate_and_use_invite(db_session, invite.code)
        
    assert exc_info.value.status_code == 400
    assert "exceeded the usage limit" in exc_info.value.detail


@pytest.mark.anyio
async def test_invite_expired(db_session):
    """
    AC 3: Expired invite.
    We test the service by injecting an expiration date in the past.
    """
    from datetime import datetime, timedelta

    from app.services.invite import InviteService
    
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    from app.repositories.invite import InviteRepository
    service = InviteService(InviteRepository())
    
    invite = await service.create_invite(
        db_session, uuid.UUID(server_id), owner_id, max_uses=10, expires_in_seconds=3600
    )
    
    invite.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
    db_session.add(invite)
    await db_session.commit()
    
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await service.validate_and_use_invite(db_session, invite.code)
        
    assert exc_info.value.status_code == 400
    assert "has expired" in exc_info.value.detail

@pytest.mark.parametrize("malformed_code", [
    "not-a-real-code-1234",
    "a" * 500,                              # way too long than String(16)
    "'; DROP TABLE server_invites; --",     # SQL injection attempt
    "código-con-ñ-y-emoji-🚀",               # characters no-ASCII
    " ",                                     # just a space
])
def test_join_with_malformed_code_returns_400_not_crash(malformed_code):
    """
    A malformed code, inexistent or potentially malicious
    should be treated as 400 invalid and never break the server
    down 500 nor filter/alter internal data.
    """
    random_user_id = str(uuid.uuid4())
    encoded_code = quote(malformed_code, safe="")

    response = client.post(
        f"/api/v1/invites/{encoded_code}/join",
        headers={"x-user-id": random_user_id},
    )

    assert response.status_code == 400
    assert "no longer valid" in response.json()["detail"]


@pytest.mark.parametrize("malformed_code", [
    "not-a-real-code-1234",
    "'; DROP TABLE server_invites; --",
])
def test_revoke_with_malformed_code_returns_404_not_crash(malformed_code):
    """
    Revoke an non-existent code(or malformed) should give 404,
    not 400 or stacj tarce
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    encoded_code = quote(malformed_code, safe="")

    response = client.delete(
        f"/api/v1/servers/{server_id}/invites/{encoded_code}",
        headers={"x-user-id": owner_id},
    )

    assert response.status_code == 404

def test_join_server_success():
    """
    Given a valid active invite
    When a new user attempts to join using the code
    Then they successfully join and the server_id is returned.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    
    res_create = client.post(
        f"/api/v1/servers/{server_id}/invites", 
        json={"max_uses": 10}, 
        headers={"x-user-id": owner_id}
    )
    code = res_create.json()["code"]
    
    new_user_id = str(uuid.uuid4())
    res_join = client.post(
        f"/api/v1/invites/{code}/join", 
        headers={"x-user-id": new_user_id}
    )
    
    assert res_join.status_code == 200
    assert res_join.json()["server_id"] == server_id

def test_revoke_invite_without_permissions():
    """
    Given an active invite
    When a user without permissions (or not in the server) tries to revoke it
    Then it returns a 403 Forbidden.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    
    res_create = client.post(
        f"/api/v1/servers/{server_id}/invites", 
        json={"max_uses": 10}, 
        headers={"x-user-id": owner_id}
    )
    code = res_create.json()["code"]
    
    random_user_id = str(uuid.uuid4())
    res_revoke = client.delete(
        f"/api/v1/servers/{server_id}/invites/{code}", 
        headers={"x-user-id": random_user_id}
    )
    
    assert res_revoke.status_code == 403

def test_join_already_member():
    """
    Given an active invite
    When a user who is already a member uses it
    Then the system should handle it idempotently and return 200.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    
    res_create = client.post(
        f"/api/v1/servers/{server_id}/invites", 
        json={"max_uses": 10}, 
        headers={"x-user-id": owner_id}
    )
    code = res_create.json()["code"]
    
    # owner joining their own server
    res_join = client.post(
        f"/api/v1/invites/{code}/join", 
        headers={"x-user-id": owner_id}
    )
    
    assert res_join.status_code == 200
    assert res_join.json()["server_id"] == server_id
def test_get_invite_preview_success():
    """
    Given a valid active invite
    When a user fetches the invite preview
    Then it returns the server name, icon, description and member count.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    
    res_create = client.post(
        f"/api/v1/servers/{server_id}/invites", 
        json={"max_uses": 10}, 
        headers={"x-user-id": owner_id}
    )
    code = res_create.json()["code"]
    
    new_user_id = str(uuid.uuid4())
    res_preview = client.get(
        f"/api/v1/invites/{code}", 
        headers={"x-user-id": new_user_id}
    )
    
    assert res_preview.status_code == 200
    data = res_preview.json()
    assert data["server_id"] == server_id
    assert data["code"] == code
    assert "server_name" in data
    assert data["member_count"] >= 1

def test_get_invite_preview_invalid_code():
    """
    Given an invalid or revoked invite code
    When a user fetches the invite preview
    Then it returns a 404 Not Found error.
    """
    new_user_id = str(uuid.uuid4())
    res_preview = client.get(
        "/api/v1/invites/invalid-code-xyz", 
        headers={"x-user-id": new_user_id}
    )
    assert res_preview.status_code == 404
