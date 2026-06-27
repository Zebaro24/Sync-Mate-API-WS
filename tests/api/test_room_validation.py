from datetime import datetime, timezone

from app.modules.room.dependencies import _room_service
from app.modules.room.models import Room
from tests.client import client

REZKA_URL = "https://rezka.ag/films/fantasy/12345-example.html"


def test_create_room_rejects_non_rezka_url():
    response = client.post("/api/rooms", json={"name": "Room", "video_url": "https://example.com/x.mp4"})
    assert response.status_code == 422


def test_create_room_accepts_rezka_url():
    response = client.post("/api/rooms", json={"name": "Room", "video_url": REZKA_URL})
    assert response.status_code == 201
    assert response.json()["video_url"] == REZKA_URL


def test_update_room_rejects_non_rezka_url():
    created = client.post("/api/rooms", json={"name": "Room", "video_url": REZKA_URL})
    room_id = created.json()["room_id"]
    response = client.patch(f"/api/rooms/{room_id}", json={"video_url": "http://evil.test/x"})
    assert response.status_code == 422


def test_redirect_to_rezka_video():
    created = client.post("/api/rooms", json={"name": "Room", "video_url": REZKA_URL})
    room_id = created.json()["room_id"]
    response = client.get(f"/api/rooms/{room_id}/redirect", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == REZKA_URL


def test_redirect_rejects_non_rezka_video():
    # Подкладываем комнату с недопустимым URL напрямую, минуя валидацию схемы.
    room = Room("bad", "Room", "https://example.com/x.mp4", 0.0, created_at=datetime.now(timezone.utc))
    _room_service._storage["bad"] = room
    response = client.get("/api/rooms/bad/redirect", follow_redirects=False)
    assert response.status_code == 400
