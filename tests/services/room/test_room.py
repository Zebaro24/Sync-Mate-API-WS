from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.room.models import Room


@pytest.fixture(autouse=True)
def mock_settings(mocker):
    fake_settings = MagicMock()
    fake_settings.REQUIRED_DOWNLOAD_TIME = 5
    mocker.patch("app.modules.room.models.settings", fake_settings)
    return fake_settings


@pytest.fixture
def mock_user():
    websocket = AsyncMock()
    websocket.client = "test_client"
    user = MagicMock()
    user.websocket = websocket
    user.current_time = 0
    user.downloaded_time = 10
    return user


@pytest.mark.asyncio
async def test_room_add_and_remove_user(mock_user):
    room = Room("1", "TestRoom", "video.mp4", 0, created_at="now")

    await room.add_user(mock_user)
    assert mock_user in room.user_storage

    await room.remove_user(mock_user)
    assert mock_user not in room.user_storage


@pytest.mark.asyncio
async def test_remove_user_is_idempotent(mock_user):
    """Повторный remove_user не должен бросать ValueError."""
    room = Room("1", "TestRoom", "video.mp4", 0, created_at="now")
    await room.add_user(mock_user)
    await room.remove_user(mock_user)
    await room.remove_user(mock_user)  # не должно падать
    assert mock_user not in room.user_storage


@pytest.mark.asyncio
async def test_set_video_and_get_users_exc(mock_user):
    room = Room("1", "TestRoom", "video.mp4", 0, created_at="now")
    await room.add_user(mock_user)

    room.set_video("new_video.mp4", 42)
    assert room.video_url == "new_video.mp4"
    assert room.current_time == 42

    result = room.get_users_exc(mock_user)
    assert result == []


def test_load_sets_state_correctly():
    room = Room("1", "TestRoom", "video.mp4", 10, created_at="now")
    room.load(20)
    assert room.current_time == 20
    assert not room.is_loaded


@pytest.mark.asyncio
async def test_check_is_loaded_true(mock_user, mock_settings):
    room = Room("1", "Room1", "video.mp4", 0, created_at="now")
    await room.add_user(mock_user)

    mock_user.current_time = 0
    mock_user.downloaded_time = 10

    result = await room.check_is_loaded(check_user=mock_user)

    assert result is True
    assert room.is_loaded is True
    mock_user.websocket.send_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_is_loaded_false_due_to_download_time(mock_user, mock_settings):
    room = Room("1", "Room1", "video.mp4", 0, created_at="now")
    await room.add_user(mock_user)

    mock_user.downloaded_time = 2  # меньше REQUIRED_DOWNLOAD_TIME
    result = await room.check_is_loaded(check_user=mock_user)

    assert result is False
    assert room.is_loaded is False


@pytest.mark.asyncio
async def test_play_sends_play_to_all(mock_user):
    room = Room("1", "Room1", "video.mp4", 0, created_at="now")
    await room.add_user(mock_user)

    await room.play()
    mock_user.websocket.send_json.assert_awaited_once_with({"type": "play"})


@pytest.mark.asyncio
async def test_pause_excludes_user(mock_user):
    room = Room("1", "Room1", "video.mp4", 0, created_at="now")
    user2 = MagicMock()
    user2.websocket = AsyncMock()
    user2.current_time = 0
    user2.downloaded_time = 10

    await room.add_user(mock_user)
    await room.add_user(user2)

    await room.pause(exception_user=mock_user)
    mock_user.websocket.send_json.assert_not_awaited()
    user2.websocket.send_json.assert_awaited_once_with({"type": "pause"})


@pytest.mark.asyncio
async def test_seek_sends_to_all_except_one(mock_user):
    room = Room("1", "Room1", "video.mp4", 0, created_at="now")
    user2 = MagicMock()
    user2.websocket = AsyncMock()
    user2.current_time = 0
    user2.downloaded_time = 10

    await room.add_user(mock_user)
    await room.add_user(user2)

    await room.seek(15, exception_user=mock_user)
    mock_user.websocket.send_json.assert_not_awaited()
    user2.websocket.send_json.assert_awaited_once_with({"type": "seek", "current_time": 15})


@pytest.mark.asyncio
async def test_seek_specific_user(mock_user):
    room = Room("1", "Room1", "video.mp4", 0, created_at="now")
    await room.seek(10, user=mock_user)
    mock_user.websocket.send_json.assert_awaited_once_with({"type": "seek", "current_time": 10})


@pytest.mark.asyncio
async def test_remove_block_pause(mock_user):
    room = Room("1", "Room1", "video.mp4", 0, created_at="now")
    await room.add_user(mock_user)
    await room.remove_block_pause()
    mock_user.websocket.send_json.assert_awaited_once_with({"type": "remove_block_pause"})
