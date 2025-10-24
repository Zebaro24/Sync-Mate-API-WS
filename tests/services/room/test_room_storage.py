from unittest.mock import MagicMock

import pytest

from app.services.room.room import Room
from app.services.room.room_storage import RoomStorage


@pytest.fixture
def room_schema():
    schema = MagicMock()
    schema.model_dump.return_value = {
        "room_id": "123",
        "name": "TestRoom",
        "video_url": "video.mp4",
        "current_time": 0,
        "created_at": "now",
    }
    return schema


@pytest.fixture
def storage():
    return RoomStorage()


def test_create_room(storage, room_schema):
    room = storage.create_room(room_schema)
    assert isinstance(room, Room)
    assert "123" in storage.storage
    assert storage.storage["123"] == room
    assert room.name == "TestRoom"


def test_get_room_existing(storage, room_schema):
    created = storage.create_room(room_schema)
    found = storage.get_room("123")
    assert found == created


def test_get_room_non_existing(storage):
    assert storage.get_room("not_exist") is None


def test_delete_room_when_empty(storage, room_schema):
    room = storage.create_room(room_schema)
    room.user_storage = []
    result = storage.delete_room("123")
    assert result is True
    assert "123" not in storage.storage


def test_delete_room_when_has_users(storage, room_schema):
    room = storage.create_room(room_schema)
    fake_user = MagicMock()
    room.user_storage = [fake_user]
    result = storage.delete_room("123")
    assert result is False
    assert "123" in storage.storage
