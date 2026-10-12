from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def create_test_server(owner_id: str) -> str:
    response = client.post("/api/v1/servers", data={"name": "Reorder Test Server"}, headers={"x-user-id": owner_id})
    return response.json()["id"]


def create_test_channel(server_id: str, owner_id: str, name: str, category_id: str | None = None) -> str:
    payload = {"name": name, "type": "text"}
    if category_id:
        payload["category_id"] = category_id
    response = client.post(
        f"/api/v1/servers/{server_id}/channels", json=payload, headers={"x-user-id": owner_id}
    )
    return response.json()["id"]


def create_test_category(server_id: str, owner_id: str, name: str) -> str:
    response = client.post(
        f"/api/v1/servers/{server_id}/categories", json={"name": name}, headers={"x-user-id": owner_id}
    )
    return response.json()["id"]


def get_server(server_id: str, user_id: str) -> dict:
    servers = client.get("/api/v1/servers", headers={"x-user-id": user_id}).json()
    return next(s for s in servers if s["id"] == server_id)


def join_as_member(server_id: str, owner_id: str) -> str:
    """Joins a new user through an invite: a member with the default permissions (no MANAGE_CHANNELS)."""
    code = client.post(
        f"/api/v1/servers/{server_id}/invites", json={"max_uses": 10}, headers={"x-user-id": owner_id}
    ).json()["code"]
    member_id = str(uuid.uuid4())
    client.post(f"/api/v1/invites/{code}/join", headers={"x-user-id": member_id})
    return member_id


def channel_order_payload(server: dict, ordered_ids: list[str], category_by_id: dict | None = None) -> dict:
    category_by_id = category_by_id or {}
    current = {c["id"]: c["category_id"] for c in server["channels"]}
    return {
        "channels": [
            {"id": cid, "category_id": category_by_id.get(cid, current[cid])} for cid in ordered_ids
        ]
    }


# ---------- Canales ----------


def test_reorder_channels_success_is_persisted():
    """
    CA 1: Successful reorder
    GIVEN a user with permissions moves a channel to a new position
    WHEN they confirm the change
    THEN the new order is persisted and every member sees it
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    create_test_channel(server_id, owner_id, "alpha")
    create_test_channel(server_id, owner_id, "beta")
    server = get_server(server_id, owner_id)
    reversed_ids = [c["id"] for c in reversed(server["channels"])]

    response = client.put(
        f"/api/v1/servers/{server_id}/channels/order",
        json=channel_order_payload(server, reversed_ids),
        headers={"x-user-id": owner_id},
    )

    assert response.status_code == 200
    assert [c["id"] for c in response.json()] == reversed_ids
    assert [c["position"] for c in response.json()] == list(range(len(reversed_ids)))

    member_id = join_as_member(server_id, owner_id)
    assert [c["id"] for c in get_server(server_id, member_id)["channels"]] == reversed_ids


def test_reorder_channels_can_move_channel_to_another_category():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    category_id = create_test_category(server_id, owner_id, "GAMING")
    channel_id = create_test_channel(server_id, owner_id, "lobby")
    server = get_server(server_id, owner_id)
    ids = [c["id"] for c in server["channels"]]

    response = client.put(
        f"/api/v1/servers/{server_id}/channels/order",
        json=channel_order_payload(server, ids, {channel_id: category_id}),
        headers={"x-user-id": owner_id},
    )

    assert response.status_code == 200
    moved = next(c for c in response.json() if c["id"] == channel_id)
    assert moved["category_id"] == category_id


def test_reorder_channels_without_permissions_fails():
    """
    CA 2: No permissions
    GIVEN a member without administration permissions tries to reorder channels
    WHEN they try it
    THEN the system does not allow it
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    create_test_channel(server_id, owner_id, "alpha")
    server = get_server(server_id, owner_id)
    original_ids = [c["id"] for c in server["channels"]]
    member_id = join_as_member(server_id, owner_id)

    response = client.put(
        f"/api/v1/servers/{server_id}/channels/order",
        json=channel_order_payload(server, list(reversed(original_ids))),
        headers={"x-user-id": member_id},
    )

    assert response.status_code == 403
    assert [c["id"] for c in get_server(server_id, owner_id)["channels"]] == original_ids


def test_reorder_channels_non_member_fails():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    server = get_server(server_id, owner_id)

    response = client.put(
        f"/api/v1/servers/{server_id}/channels/order",
        json=channel_order_payload(server, [c["id"] for c in server["channels"]]),
        headers={"x-user-id": str(uuid.uuid4())},
    )

    assert response.status_code == 403


def test_reorder_channels_fails_if_a_channel_is_missing():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    create_test_channel(server_id, owner_id, "alpha")
    server = get_server(server_id, owner_id)
    ids = [c["id"] for c in server["channels"]]

    response = client.put(
        f"/api/v1/servers/{server_id}/channels/order",
        json=channel_order_payload(server, ids[:-1]),
        headers={"x-user-id": owner_id},
    )

    assert response.status_code == 400


def test_reorder_channels_fails_with_duplicated_channel():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    server = get_server(server_id, owner_id)
    ids = [c["id"] for c in server["channels"]]

    response = client.put(
        f"/api/v1/servers/{server_id}/channels/order",
        json=channel_order_payload(server, ids + [ids[0]]),
        headers={"x-user-id": owner_id},
    )

    assert response.status_code == 400


def test_reorder_channels_fails_with_channel_of_another_server():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    other_server_id = create_test_server(owner_id)
    foreign_channel_id = create_test_channel(other_server_id, owner_id, "foreign")
    server = get_server(server_id, owner_id)
    payload = channel_order_payload(server, [c["id"] for c in server["channels"]])
    payload["channels"].append({"id": foreign_channel_id, "category_id": None})

    response = client.put(
        f"/api/v1/servers/{server_id}/channels/order", json=payload, headers={"x-user-id": owner_id}
    )

    assert response.status_code == 400


def test_reorder_channels_fails_with_category_of_another_server():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    other_server_id = create_test_server(owner_id)
    foreign_category_id = create_test_category(other_server_id, owner_id, "FOREIGN")
    channel_id = create_test_channel(server_id, owner_id, "alpha")
    server = get_server(server_id, owner_id)

    response = client.put(
        f"/api/v1/servers/{server_id}/channels/order",
        json=channel_order_payload(server, [c["id"] for c in server["channels"]], {channel_id: foreign_category_id}),
        headers={"x-user-id": owner_id},
    )

    assert response.status_code == 404


def test_reorder_channels_fails_with_duplicate_name_in_target_category():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    category_id = create_test_category(server_id, owner_id, "GAMING")
    create_test_channel(server_id, owner_id, "lobby", category_id=category_id)
    loose_lobby_id = create_test_channel(server_id, owner_id, "lobby")
    server = get_server(server_id, owner_id)

    response = client.put(
        f"/api/v1/servers/{server_id}/channels/order",
        json=channel_order_payload(server, [c["id"] for c in server["channels"]], {loose_lobby_id: category_id}),
        headers={"x-user-id": owner_id},
    )

    assert response.status_code == 400


def test_reorder_channels_rejects_client_positions():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    server = get_server(server_id, owner_id)
    payload = channel_order_payload(server, [c["id"] for c in server["channels"]])
    payload["channels"][0]["position"] = 99

    response = client.put(
        f"/api/v1/servers/{server_id}/channels/order", json=payload, headers={"x-user-id": owner_id}
    )

    assert response.status_code == 422


# ---------- Categorías ----------


def test_reorder_categories_success_is_persisted():
    """
    CA 1: Successful reorder of categories
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    first = create_test_category(server_id, owner_id, "FIRST")
    second = create_test_category(server_id, owner_id, "SECOND")

    response = client.put(
        f"/api/v1/servers/{server_id}/categories/order",
        json={"category_ids": [second, first]},
        headers={"x-user-id": owner_id},
    )

    assert response.status_code == 200
    assert [c["id"] for c in response.json()] == [second, first]
    assert [c["id"] for c in get_server(server_id, owner_id)["categories"]] == [second, first]


def test_reorder_categories_without_permissions_fails():
    """
    CA 2: No permissions to reorder categories
    """
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    first = create_test_category(server_id, owner_id, "FIRST")
    second = create_test_category(server_id, owner_id, "SECOND")
    member_id = join_as_member(server_id, owner_id)

    response = client.put(
        f"/api/v1/servers/{server_id}/categories/order",
        json={"category_ids": [second, first]},
        headers={"x-user-id": member_id},
    )

    assert response.status_code == 403
    assert [c["id"] for c in get_server(server_id, owner_id)["categories"]] == [first, second]


def test_reorder_categories_fails_if_a_category_is_missing():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    first = create_test_category(server_id, owner_id, "FIRST")
    create_test_category(server_id, owner_id, "SECOND")

    response = client.put(
        f"/api/v1/servers/{server_id}/categories/order",
        json={"category_ids": [first]},
        headers={"x-user-id": owner_id},
    )

    assert response.status_code == 400


def test_reorder_categories_fails_with_category_of_another_server():
    owner_id = str(uuid.uuid4())
    server_id = create_test_server(owner_id)
    other_server_id = create_test_server(owner_id)
    own = create_test_category(server_id, owner_id, "OWN")
    foreign = create_test_category(other_server_id, owner_id, "FOREIGN")

    response = client.put(
        f"/api/v1/servers/{server_id}/categories/order",
        json={"category_ids": [own, foreign]},
        headers={"x-user-id": owner_id},
    )

    assert response.status_code == 400
