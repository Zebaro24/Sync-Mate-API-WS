from app.services.room.room_storage import room_storage
from tests.client import client

room_id = None
video_url = "https://rezka.ag/films/documentary/55648-god-2023.html"


def test_create_room():
    global room_id
    json_data = {
        "name": "Test1",
        "video_url": video_url,
    }
    response = client.post("/api/rooms/", json=json_data)
    assert response.status_code == 200
    room_id = response.json()["room_id"]
    assert room_id in room_storage.storage


def test_list_rooms():
    response = client.get("/api/rooms/")
    assert response.status_code == 200
    assert any(r["room_id"] == room_id for r in response.json())


def test_get_room():
    response = client.get(f"/api/rooms/{room_id}")
    assert response.status_code == 200


def test_websocket_connections():
    with (
        client.websocket_connect(f"/ws/{room_id}") as ws1,
        client.websocket_connect(f"/ws/{room_id}") as ws2,
    ):
        ws1.send_json({"type": "connect", "name": "test"})
        data = ws1.receive_json()
        assert data["type"] == "connect" and data["message"] == "success"

        ws2.send_json({"type": "connect", "name": "test2"})
        data = ws2.receive_json()
        assert data["type"] == "connect" and data["message"] == "success"

        response = client.get(f"/api/rooms/{room_id}")
        assert response.status_code == 200
        assert len(response.json()["users"]) == 2


def test_patch_room():
    response = client.patch(f"/api/rooms/{room_id}", json={"name": "Test2"})
    assert response.status_code == 200
    assert response.json()["name"] == "Test2"


def test_redirect_room():
    response = client.get(f"/api/rooms/{room_id}/redirect", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == video_url


def test_delete_room():
    response = client.delete(f"/api/rooms/{room_id}")
    assert response.status_code == 200
    assert room_id not in room_storage.storage
