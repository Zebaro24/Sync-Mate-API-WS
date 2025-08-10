from app.services.room_storage import room_storage
from tests.client import client


def test_room():
    response = client.post("/api/room/create")
    assert response.status_code == 200
    room_id = response.json()["room_id"]
    assert room_id in room_storage.storage

    with (
        client.websocket_connect(f"/ws/{room_id}") as ws1,
        client.websocket_connect(f"/ws/{room_id}") as ws2,
    ):
        data = ws1.receive_text()
        assert data == "Connection success!"

        data = ws2.receive_text()
        assert data == "Connection success!"

        ws1.send_json({"type": "play", "video_time": "1:25"})
        data = ws2.receive_json()
        assert data["video_time"] == "1:25"
