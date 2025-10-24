from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.room.user_handler import UserHandler


@pytest.mark.asyncio
async def test_send_to_room_sends_to_other_users():
    user1 = MagicMock()
    user2 = MagicMock()
    user3 = MagicMock()
    user1.websocket.send_json = AsyncMock()
    user2.websocket.send_json = AsyncMock()
    user3.websocket.send_json = AsyncMock()

    room = MagicMock()
    room.get_users_exc.return_value = [user2, user3]

    handler = UserHandler(user1, room)
    data = {"type": "info", "msg": "test"}

    await handler.send_to_room(data)

    user2.websocket.send_json.assert_awaited_once_with(data)
    user3.websocket.send_json.assert_awaited_once_with(data)
    user1.websocket.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_handle_info_updates_user_info():
    user = MagicMock()
    user.websocket = AsyncMock()
    room = MagicMock()
    handler = UserHandler(user, room)

    data = {"type": "info", "extra": "value"}
    await handler.handle(data)

    assert user.info == {"extra": "value"}


@pytest.mark.asyncio
async def test_handle_status_triggers_play_if_loaded():
    user = MagicMock()
    room = MagicMock()
    room.is_loaded = False
    room.is_paused = False
    room.check_is_loaded = AsyncMock(return_value=True)
    room.play = AsyncMock()

    handler = UserHandler(user, room)

    data = {"type": "status", "current_time": 10, "downloaded_time": 20}
    await handler.handle(data)

    room.check_is_loaded.assert_awaited_once_with(user)
    room.play.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_play_flow():
    user = MagicMock()
    room = MagicMock()
    room.check_is_loaded = AsyncMock(return_value=True)
    room.play = AsyncMock()
    room.seek = AsyncMock()

    handler = UserHandler(user, room)

    data = {"type": "play", "current_time": 50}
    await handler.handle(data)

    room.seek.assert_awaited_once_with(50, user)
    room.load.assert_called_once_with(50)
    room.play.assert_awaited_once()
    assert room.is_paused is False


@pytest.mark.asyncio
async def test_handle_pause_flow():
    user = MagicMock()
    room = MagicMock()
    room.seek = AsyncMock()

    handler = UserHandler(user, room)

    data = {"type": "pause", "current_time": 30}
    await handler.handle(data)

    room.seek.assert_awaited_once_with(30, user)
    room.load.assert_called_once_with(30)
    assert room.is_paused is True


@pytest.mark.asyncio
async def test_handle_invalid_type_does_nothing():
    user = MagicMock()
    room = MagicMock()
    handler = UserHandler(user, room)

    data = {"type": "unknown", "foo": "bar"}
    await handler.handle(data)

    # ничего не должно произойти
    room.play.assert_not_called()
    room.seek.assert_not_called()
