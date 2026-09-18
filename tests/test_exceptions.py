from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_validation_error_rfc7807_format():
    """Verify that a 422 validation error returns RFC 7807 problem json."""
    headers = {"x-user-id": "auth0|test-user"}
    response = client.post("/api/v1/servers", data={"name": ""}, headers=headers)

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    data = response.json()
    assert data["type"] == "about:blank"
    assert data["title"] == "Validation Error"
    assert data["status"] == 422
    assert data["detail"] == "One or more boundary validation rules failed."
    assert data["instance"] == "/api/v1/servers"
    assert "invalid_params" in data
    assert any("name" in p["name"] for p in data["invalid_params"])


def test_unauthenticated_error_rfc7807_format():
    """Verify that a 401 error (missing X-User-Id header) returns RFC 7807 problem json."""
    response = client.post("/api/v1/servers", data={"name": "Valid Server"})

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    data = response.json()
    assert data["type"] == "about:blank"
    assert data["title"] == "Unauthorized"
    assert data["status"] == 401
    assert "Unauthenticated user identity" in data["detail"]
    assert data["instance"] == "/api/v1/servers"


def test_bad_request_rfc7807_format():
    """Verify that a 400 Bad Request error returns RFC 7807 problem json."""
    headers = {"x-user-id": "auth0|test-user"}
    files = {"icon": ("test.pdf", b"fake content", "application/pdf")}
    response = client.post(
        "/api/v1/servers",
        data={"name": "Bad Icon Server"},
        files=files,
        headers=headers,
    )

    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"
    data = response.json()
    assert data["type"] == "about:blank"
    assert data["title"] == "Bad Request"
    assert data["status"] == 400
    assert "Unsupported format" in data["detail"]
    assert data["instance"] == "/api/v1/servers"


def test_not_found_endpoint_rfc7807_format():
    """Verify that a 404 Not Found error returns RFC 7807 problem json."""
    response = client.get("/api/v1/non-existent-endpoint")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    data = response.json()
    assert data["type"] == "about:blank"
    assert data["status"] == 404
    assert data["instance"] == "/api/v1/non-existent-endpoint"


def test_forbidden_error_rfc7807_format():
    """Verify that a 403 Forbidden error returns RFC 7807 problem json."""
    # First create a server with owner A
    owner_id = "auth0|owner-user"
    headers_owner = {"x-user-id": owner_id}
    res = client.post("/api/v1/servers", data={"name": "Permission Server"}, headers=headers_owner)
    assert res.status_code == 201
    server_id = res.json()["id"]

    # User B attempts to create a channel without permissions
    headers_other = {"x-user-id": "auth0|other-user"}
    payload = {"name": "secret-channel", "type": "text"}
    response = client.post(f"/api/v1/servers/{server_id}/channels", json=payload, headers=headers_other)

    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"
    data = response.json()
    assert data["type"] == "about:blank"
    assert data["title"] == "Forbidden"
    assert data["status"] == 403
    assert "detail" in data
    assert data["instance"] == f"/api/v1/servers/{server_id}/channels"

