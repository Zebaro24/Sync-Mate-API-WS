import pytest

from app.modules.room.dependencies import _room_service


@pytest.fixture(autouse=True)
def _reset_room_storage():
    """Изолирует тесты, использующие глобальный RoomService."""
    _room_service._storage.clear()
    yield
    _room_service._storage.clear()
