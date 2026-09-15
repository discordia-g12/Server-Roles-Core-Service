import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
fake_headers = {"x-user-id": str(uuid.uuid4())}
def test_create_server_success_generates_default_channels():
    """
    Given a user provides a valid server name and confirms creation,
    When the request is sent,
    Then the server is created, and it automatically generates a text and a voice channel.
    """
    payload = {"name": "My Awesome Gaming Server"}
    
    response = client.post("/api/v1/servers", data=payload, headers=fake_headers)
    
    assert response.status_code == 201
    data = response.json()
    
    assert data["name"] == "My Awesome Gaming Server"
    assert "id" in data
    assert "owner_id" in data
    
    channels = data.get("channels", [])
    assert len(channels) == 2
    
    channel_names = [ch["name"] for ch in channels]
    channel_types = [ch["type"] for ch in channels]
    
    assert "general" in channel_names
    assert "Voz General" in channel_names
    assert "text" in channel_types
    assert "voice" in channel_types
def test_create_server_success_with_valid_icon():
    """
    Given a user provides a valid server name and a valid image icon,
    Then the server is created successfully.
    """
    payload = {"name": "Community Hub"}
    files = {"icon": ("icon.png", b"fake_png_bytes", "image/png")}
    
    response = client.post("/api/v1/servers", data=payload, files=files, headers=fake_headers)
    
    assert response.status_code == 201
    assert response.json()["name"] == "Community Hub"
@pytest.mark.parametrize("invalid_name", [
    "",             
    "A" * 101,     
    "Bad\x00Name", 
])
def test_create_server_fails_with_invalid_name(invalid_name):
    """
    Given a user enters an empty name, an excessively long name, or a name with a null char,
    When they attempt to create the server,
    Then the system indicates an error and does not create it.
    """
    payload = {"name": invalid_name}
    
    response = client.post("/api/v1/servers", data=payload, headers=fake_headers)
    
    assert response.status_code == 422
    assert "detail" in response.json()
def test_create_server_fails_with_unsupported_icon_format():
    """
    Given a user uploads an icon with an unsupported format (e.g., PDF or GIF),
    When they attempt to create it,
    Then the system rejects the file with a descriptive error.
    """
    payload = {"name": "Invalid Icon Server"}
    files = {"icon": ("document.pdf", b"fake_pdf_bytes", "application/pdf")}
    
    response = client.post("/api/v1/servers", data=payload, files=files, headers=fake_headers)
    
    assert response.status_code == 400
    assert "Use JPEG, PNG or WebP" in response.json()["detail"]
def test_create_server_fails_with_oversized_icon():
    """
    Given a user uploads an icon that exceeds the maximum allowed size (5MB),
    When they attempt to create it,
    Then the system rejects the file with a descriptive error.
    """
    payload = {"name": "Large Icon Server"}
    large_file_bytes = b"0" * ((5 * 1024 * 1024) + 1) 
    files = {"icon": ("huge.png", large_file_bytes, "image/png")}
    
    response = client.post("/api/v1/servers", data=payload, files=files, headers=fake_headers)
    
    assert response.status_code == 400
    assert "Limit 5MB" in response.json()["detail"]


def test_create_server_success_with_auth0_user_id():
    """
    Given a request contains an Auth0 string-formatted user ID (e.g. 'auth0|123456'),
    When the server is created,
    Then the server is created successfully and owner_id preserves the Auth0 ID.
    """
    auth0_id = "auth0|66e6a1234567890abcdef123"
    payload = {"name": "Auth0 Test Guild"}
    headers = {"x-user-id": auth0_id}

    response = client.post("/api/v1/servers", data=payload, headers=headers)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Auth0 Test Guild"
    assert data["owner_id"] == auth0_id


def test_create_server_fails_when_x_user_id_header_missing():
    """
    Given a request lacks the x-user-id header,
    When the client attempts to create a server,
    Then the request is rejected with HTTP 401 Unauthorized.
    """
    payload = {"name": "Unauthenticated Server"}
    response = client.post("/api/v1/servers", data=payload)

    assert response.status_code == 401
    assert "Unauthenticated user identity" in response.json()["detail"]