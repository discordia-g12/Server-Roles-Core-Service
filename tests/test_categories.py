from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def create_test_server(owner_id: str) -> str:
    """Helper to quickly create a server before testing category operations."""
    payload = {"name": "Category Test Server"}
    headers = {"x-user-id": owner_id}
    response = client.post("/api/v1/servers", data=payload, headers=headers)
    return response.json()["id"]


def create_test_channel(server_id: str, owner_id: str, name: str = "chat", category_id: str | None = None) -> str:
    """Helper to create a channel inside a server."""
    payload = {"name": name, "type": "text"}
    if category_id:
        payload["category_id"] = category_id
    headers = {"x-user-id": owner_id}
    response = client.post(f"/api/v1/servers/{server_id}/channels", json=payload, headers=headers)
    return response.json()["id"]


def test_create_category_success():
    """
    CA 1: Create category
    GIVEN a user with permmissions defines a category name
    WHEN confirms its creation
    THEN the category stays available to group channels inside
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)

    headers = {"x-user-id": owner_id}
    payload = {"name": "TEXT CHANNELS"}

    response = client.post(f"/api/v1/servers/{server_id}/categories", json=payload, headers=headers)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "TEXT CHANNELS"
    assert data["server_id"] == server_id
    assert "id" in data
    assert "position" in data


def test_create_category_without_permissions():
    """
    CA 1: User without permissions
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)

    non_member_id = str(uuid.uuid4())
    headers = {"x-user-id": non_member_id}
    payload = {"name": "STAFF ONLY"}

    response = client.post(f"/api/v1/servers/{server_id}/categories", json=payload, headers=headers)

    assert response.status_code == 403
    assert "detail" in response.json()


def test_create_category_fails_with_duplicate_name():
    """
    CA 1: Not allowed two categories with the same name.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    headers = {"x-user-id": owner_id}
    payload = {"name": "GAMING"}

    res1 = client.post(f"/api/v1/servers/{server_id}/categories", json=payload, headers=headers)
    assert res1.status_code == 201

    res2 = client.post(f"/api/v1/servers/{server_id}/categories", json=payload, headers=headers)
    assert res2.status_code == 400
    assert "detail" in res2.json()


@pytest.mark.parametrize("invalid_name", ["", "A" * 101])
def test_create_category_fails_with_invalid_name(invalid_name):
    """
    CA 1: Validating category name lenght.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    headers = {"x-user-id": owner_id}

    response = client.post(
        f"/api/v1/servers/{server_id}/categories", json={"name": invalid_name}, headers=headers
    )
    assert response.status_code == 422


def test_get_categories():
    """
    CA 1: List all created categories in a server.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    headers = {"x-user-id": owner_id}

    client.post(f"/api/v1/servers/{server_id}/categories", json={"name": "CAT 1"}, headers=headers)
    client.post(f"/api/v1/servers/{server_id}/categories", json={"name": "CAT 2"}, headers=headers)

    response = client.get(f"/api/v1/servers/{server_id}/categories", headers=headers)
    assert response.status_code == 200
    categories = response.json()
    assert len(categories) == 2
    category_names = [c["name"] for c in categories]
    assert "CAT 1" in category_names
    assert "CAT 2" in category_names


def test_move_channel_to_category_success():
    """
    CA 2: Move channel to a category
    GIVEN a user with permission chooses an existing channel
    WHEN it asigns it to a category
    THEN  the channel shows grouped by that category to all members
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    headers = {"x-user-id": owner_id}

    channel_id = create_test_channel(server_id, owner_id, name="community-chat")

    cat_res = client.post(
        f"/api/v1/servers/{server_id}/categories", json={"name": "COMMUNITY"}, headers=headers
    )
    category_id = cat_res.json()["id"]

    patch_res = client.patch(
        f"/api/v1/servers/{server_id}/channels/{channel_id}",
        json={"category_id": category_id},
        headers=headers,
    )

    assert patch_res.status_code == 200
    data = patch_res.json()
    assert data["id"] == channel_id
    assert data["category_id"] == category_id


def test_move_channel_to_nonexistent_category_fails():
    """
    CA 2: Moving a channel to an unexisting category shold return 404.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    headers = {"x-user-id": owner_id}

    channel_id = create_test_channel(server_id, owner_id, name="lonely-channel")
    fake_cat_id = str(uuid.uuid4())

    patch_res = client.patch(
        f"/api/v1/servers/{server_id}/channels/{channel_id}",
        json={"category_id": fake_cat_id},
        headers=headers,
    )

    assert patch_res.status_code == 404
    assert "detail" in patch_res.json()


def test_move_channel_duplicate_name_in_target_category_fails():
    """
    CA 2: It should not allow moving a channel to a category if that category has already that channel name.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    headers = {"x-user-id": owner_id}

    cat_res = client.post(
        f"/api/v1/servers/{server_id}/categories", json={"name": "ANNOUNCEMENTS"}, headers=headers
    )
    category_id = cat_res.json()["id"]

    create_test_channel(server_id, owner_id, name="news", category_id=category_id)

    other_channel_id = create_test_channel(server_id, owner_id, name="news")

    patch_res = client.patch(
        f"/api/v1/servers/{server_id}/channels/{other_channel_id}",
        json={"category_id": category_id},
        headers=headers,
    )

    assert patch_res.status_code == 400
    assert "detail" in patch_res.json()



def test_channel_without_category_initial_state():
    """
    CA 3: Channel without category
    GIVEN a channels is not assigned to a category
    WHEN the members list the server channels
    THEN the channels shows without any category group.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    headers = {"x-user-id": owner_id}

    servers_res = client.get("/api/v1/servers", headers=headers)
    assert servers_res.status_code == 200
    server_data = next(s for s in servers_res.json() if s["id"] == server_id)

    channels = server_data["channels"]
    assert len(channels) >= 2
    for channel in channels:
        assert channel["category_id"] is None


def test_unassign_channel_from_category():
    """
    CA 3: Move a channel outside the category.
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    headers = {"x-user-id": owner_id}

    cat_res = client.post(
        f"/api/v1/servers/{server_id}/categories", json={"name": "TEMPORARY"}, headers=headers
    )
    category_id = cat_res.json()["id"]

    channel_id = create_test_channel(server_id, owner_id, name="temp-chat", category_id=category_id)

    patch_res = client.patch(
        f"/api/v1/servers/{server_id}/channels/{channel_id}",
        json={"category_id": None},
        headers=headers,
    )

    assert patch_res.status_code == 200
    assert patch_res.json()["category_id"] is None
