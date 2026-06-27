from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.room.models import Room


@pytest.fixture(autouse=True)
def mock_settings(mocker):
    fake_settings = MagicMock()
    fake_settings.REQUIRED_DOWNLOAD_TIME = 5
    fake_settings.SYNC_TOLERANCE = 1.0
    fake_settings.READY_TIMEOUT = 30.0
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
    user.duration = 0.0
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
async def test_check_is_loaded_within_tolerance(mock_user, mock_settings):
    """Небольшое расхождение позиции (в пределах допуска) не мешает готовности."""
    room = Room("1", "Room1", "video.mp4", 0, created_at="now")
    await room.add_user(mock_user)

    mock_user.current_time = 0.5  # < SYNC_TOLERANCE (1.0)
    mock_user.downloaded_time = 10

    result = await room.check_is_loaded(check_user=mock_user)

    assert result is True
    mock_user.websocket.send_json.assert_not_awaited()  # никого не дёргаем seek'ом


@pytest.mark.asyncio
async def test_check_is_loaded_seeks_laggard_beyond_tolerance(mock_user, mock_settings):
    """Расхождение больше допуска — отстающего возвращаем seek'ом, готовности нет."""
    room = Room("1", "Room1", "video.mp4", 0, created_at="now")
    await room.add_user(mock_user)

    mock_user.current_time = 5  # > SYNC_TOLERANCE
    mock_user.downloaded_time = 10

    result = await room.check_is_loaded(check_user=mock_user)

    assert result is False
    mock_user.websocket.send_json.assert_awaited_once_with({"type": "seek", "current_time": 0})


@pytest.mark.asyncio
async def test_check_is_loaded_end_of_video(mock_user, mock_settings):
    """У конца ролика остаток меньше REQUIRED_DOWNLOAD_TIME — буфера всё равно хватает."""
    room = Room("1", "Room1", "video.mp4", 98, created_at="now")
    await room.add_user(mock_user)

    mock_user.current_time = 98
    mock_user.duration = 100.0  # до конца 2 сек
    mock_user.downloaded_time = 2  # меньше REQUIRED_DOWNLOAD_TIME (5), но достаточно

    result = await room.check_is_loaded(check_user=mock_user)

    assert result is True


@pytest.mark.asyncio
async def test_add_user_resets_is_loaded(mock_user):
    """Новый участник сбрасывает признак готовности комнаты."""
    room = Room("1", "Room1", "video.mp4", 0, created_at="now")
    room.is_loaded = True
    await room.add_user(mock_user)
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


def _make_user(current_time=0, downloaded_time=10):
    user = MagicMock()
    user.websocket = AsyncMock()
    user.current_time = current_time
    user.downloaded_time = downloaded_time
    user.duration = 0.0
    return user


@pytest.mark.asyncio
async def test_remove_user_starts_when_remaining_ready(mock_settings):
    """SYNC-4: уход тормозящего делает оставшихся готовыми — им уходит play."""
    room = Room("1", "Room1", "video.mp4", 0, created_at="now")
    ready = _make_user(current_time=0, downloaded_time=10)
    laggard = _make_user(current_time=50, downloaded_time=0)

    await room.add_user(ready)
    await room.add_user(laggard)
    assert room.is_loaded is False

    await room.remove_user(laggard)

    assert room.is_loaded is True
    ready.websocket.send_json.assert_awaited_once_with({"type": "play"})


@pytest.mark.asyncio
async def test_remove_user_sends_remove_block_pause_when_paused(mock_settings):
    """SYNC-4: если комната на паузе — оставшимся уходит remove_block_pause."""
    room = Room("1", "Room1", "video.mp4", 0, created_at="now")
    room.is_paused = True
    ready = _make_user(current_time=0, downloaded_time=10)
    laggard = _make_user(current_time=50, downloaded_time=0)

    await room.add_user(ready)
    await room.add_user(laggard)

    await room.remove_user(laggard)

    assert room.is_loaded is True
    ready.websocket.send_json.assert_awaited_once_with({"type": "remove_block_pause"})


@pytest.mark.asyncio
async def test_remove_user_no_start_when_remaining_not_ready(mock_settings):
    """SYNC-4: если оставшийся всё ещё не готов — запуска нет."""
    room = Room("1", "Room1", "video.mp4", 0, created_at="now")
    not_ready = _make_user(current_time=0, downloaded_time=0)
    laggard = _make_user(current_time=50, downloaded_time=0)

    await room.add_user(not_ready)
    await room.add_user(laggard)

    await room.remove_user(laggard)

    assert room.is_loaded is False
    not_ready.websocket.send_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_remove_last_user_does_not_start(mock_settings):
    """SYNC-4: выход последнего участника не должен ничего рассылать."""
    room = Room("1", "Room1", "video.mp4", 0, created_at="now")
    user = _make_user()
    await room.add_user(user)

    await room.remove_user(user)

    assert room.is_loaded is False
    user.websocket.send_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_remove_user_does_not_replay_when_already_loaded(mock_settings):
    """SYNC-4: уже запущенная комната не шлёт повторный play при выходе участника."""
    room = Room("1", "Room1", "video.mp4", 0, created_at="now")
    room.is_loaded = True
    ready = _make_user(current_time=0, downloaded_time=10)
    other = _make_user(current_time=0, downloaded_time=10)

    room.user_storage = [ready, other]

    await room.remove_user(other)

    ready.websocket.send_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_video_resets_user_state(mock_user):
    """SYNC-6: смена видео обнуляет буфер и сбрасывает позицию участников."""
    room = Room("1", "Room1", "video.mp4", 0, created_at="now")
    mock_user.current_time = 100
    mock_user.downloaded_time = 50
    await room.add_user(mock_user)

    room.set_video("https://rezka.ag/new.html", 5)

    assert mock_user.current_time == 5
    assert mock_user.downloaded_time == 0.0


@pytest.mark.asyncio
async def test_check_is_loaded_returns_false_when_already_loaded(mock_user, mock_settings):
    """BE-4: повторный вызов на уже загруженной комнате не даёт второй play."""
    room = Room("1", "Room1", "video.mp4", 0, created_at="now")
    await room.add_user(mock_user)
    mock_user.current_time = 0
    mock_user.downloaded_time = 10

    first = await room.check_is_loaded(check_user=mock_user)
    second = await room.check_is_loaded(check_user=mock_user)

    assert first is True
    assert second is False
    assert room.is_loaded is True


@pytest.mark.asyncio
async def test_check_is_loaded_timeout_starts_ready_users(mock_settings):
    """SYNC-5: после READY_TIMEOUT стартуем по готовым — им play, отстающим seek."""
    room = Room("1", "Room1", "video.mp4", 0, created_at="now")
    ready = _make_user(current_time=0, downloaded_time=10)
    laggard = _make_user(current_time=50, downloaded_time=0)

    await room.add_user(ready)
    await room.add_user(laggard)
    room._wait_started_at = 0.0

    result = await room.check_is_loaded(check_user=ready, now=mock_settings.READY_TIMEOUT + 1.0)

    assert room.is_loaded is True
    assert result is False  # старт по таймауту обрабатывается внутри, не через возврат
    ready.websocket.send_json.assert_awaited_once_with({"type": "play"})
    laggard.websocket.send_json.assert_awaited_once_with({"type": "seek", "current_time": 0})


@pytest.mark.asyncio
async def test_check_is_loaded_timeout_remove_block_pause_when_paused(mock_settings):
    """SYNC-5: на паузе таймаут шлёт готовым remove_block_pause, а не play."""
    room = Room("1", "Room1", "video.mp4", 0, created_at="now")
    room.is_paused = True
    ready = _make_user(current_time=0, downloaded_time=10)
    laggard = _make_user(current_time=50, downloaded_time=0)

    await room.add_user(ready)
    await room.add_user(laggard)
    room._wait_started_at = 0.0

    await room.check_is_loaded(check_user=ready, now=mock_settings.READY_TIMEOUT + 1.0)

    assert room.is_loaded is True
    ready.websocket.send_json.assert_awaited_once_with({"type": "remove_block_pause"})


@pytest.mark.asyncio
async def test_check_is_loaded_no_timeout_before_deadline(mock_settings):
    """SYNC-5: до истечения READY_TIMEOUT готовому play не уходит."""
    room = Room("1", "Room1", "video.mp4", 0, created_at="now")
    ready = _make_user(current_time=0, downloaded_time=10)
    laggard = _make_user(current_time=50, downloaded_time=0)

    await room.add_user(ready)
    await room.add_user(laggard)
    room._wait_started_at = 0.0

    result = await room.check_is_loaded(check_user=ready, now=mock_settings.READY_TIMEOUT - 1.0)

    assert room.is_loaded is False
    assert result is False
    ready.websocket.send_json.assert_not_awaited()
    laggard.websocket.send_json.assert_awaited_once_with({"type": "seek", "current_time": 0})


@pytest.mark.asyncio
async def test_check_is_loaded_timeout_needs_a_ready_user(mock_settings):
    """SYNC-5: если по таймауту готовых нет — не стартуем (некого запускать)."""
    room = Room("1", "Room1", "video.mp4", 0, created_at="now")
    only = _make_user(current_time=50, downloaded_time=0)

    await room.add_user(only)
    room._wait_started_at = 0.0

    result = await room.check_is_loaded(check_user=only, now=mock_settings.READY_TIMEOUT + 1.0)

    assert room.is_loaded is False
    assert result is False
    only.websocket.send_json.assert_awaited_once_with({"type": "seek", "current_time": 0})
