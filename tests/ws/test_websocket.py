import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import ANY

import pytest

from app.services.room.room_storage import room_storage
from app.ws.websocket import websocket_endpoint


@pytest.mark.asyncio
async def test_websocket_successful_connection(mocker):
    messages = [{"type": "connect", "name": "TestUser"}, {"type": "info"}]
    side_effect = messages + [asyncio.CancelledError()]

    mock_ws: Any = SimpleNamespace(
        client="127.0.0.1",
        accept=mocker.AsyncMock(),
        close=mocker.AsyncMock(),
        send_json=mocker.AsyncMock(),
        receive_json=mocker.AsyncMock(side_effect=side_effect),
    )

    mock_room = SimpleNamespace(
        add_user=mocker.Mock(),
        remove_user=mocker.Mock(),
    )
    mocker.patch.object(room_storage, "get_room", return_value=mock_room)

    mocker.patch("app.ws.websocket.UserHandler.handle", new=mocker.AsyncMock())

    with pytest.raises(asyncio.CancelledError):
        await websocket_endpoint(mock_ws, "room123")

    mock_ws.accept.assert_awaited_once()
    mock_room.add_user.assert_called_once()
    mock_ws.send_json.assert_awaited_with({"type": "connect", "id": ANY})
    mock_room.remove_user.assert_called_once()


@pytest.mark.asyncio
async def test_room_not_found(mocker):
    mock_ws: Any = SimpleNamespace(
        client="127.0.0.1",
        accept=mocker.AsyncMock(),
        close=mocker.AsyncMock(),
        receive_json=mocker.AsyncMock(return_value={"type": "connect", "name": "TestUser"}),
        send_json=mocker.AsyncMock(),
    )

    mocker.patch.object(room_storage, "get_room", return_value=None)

    await websocket_endpoint(mock_ws, "nonexistent_room")

    mock_ws.accept.assert_awaited_once()
    mock_ws.close.assert_awaited_once_with(code=4000, reason="Room not found")


@pytest.mark.asyncio
async def test_invalid_connection_message(mocker):
    mock_ws: Any = SimpleNamespace(
        client="127.0.0.1",
        accept=mocker.AsyncMock(),
        close=mocker.AsyncMock(),
        receive_json=mocker.AsyncMock(return_value={"type": "wrong_type"}),
        send_json=mocker.AsyncMock(),
    )

    mocker.patch.object(
        room_storage, "get_room", return_value=SimpleNamespace(add_user=mocker.Mock(), remove_user=mocker.Mock())
    )

    await websocket_endpoint(mock_ws, "room123")

    mock_ws.accept.assert_awaited_once()
    mock_ws.close.assert_awaited_once_with(code=4001, reason="Authentication is required")


@pytest.mark.asyncio
async def test_exception_in_handle(mocker):
    mock_ws: Any = SimpleNamespace(
        client="127.0.0.1",
        accept=mocker.AsyncMock(),
        close=mocker.AsyncMock(),
        send_json=mocker.AsyncMock(),
        receive_json=mocker.AsyncMock(side_effect=[{"type": "connect", "name": "TestUser"}, Exception("test error")]),
    )

    mock_room = SimpleNamespace(add_user=mocker.Mock(), remove_user=mocker.Mock())
    mocker.patch.object(room_storage, "get_room", return_value=mock_room)

    mocker.patch("app.ws.websocket.UserHandler.handle", new=mocker.AsyncMock(side_effect=[Exception("test error")]))

    await websocket_endpoint(mock_ws, "room123")

    mock_ws.accept.assert_awaited_once()
    mock_ws.close.assert_awaited_once_with(code=1011)
    mock_room.remove_user.assert_called_once()


@pytest.mark.asyncio
async def test_multiple_messages(mocker):
    messages = [{"type": "connect", "name": "TestUser"}, {"type": "info"}, {"type": "status"}]
    side_effect = messages + [asyncio.CancelledError()]

    mock_ws: Any = SimpleNamespace(
        client="127.0.0.1",
        accept=mocker.AsyncMock(),
        close=mocker.AsyncMock(),
        send_json=mocker.AsyncMock(),
        receive_json=mocker.AsyncMock(side_effect=side_effect),
    )

    mock_room = SimpleNamespace(add_user=mocker.Mock(), remove_user=mocker.Mock())
    mocker.patch.object(room_storage, "get_room", return_value=mock_room)

    mock_handle = mocker.patch("app.ws.websocket.UserHandler.handle", new=mocker.AsyncMock())

    with pytest.raises(asyncio.CancelledError):
        await websocket_endpoint(mock_ws, "room123")

    assert mock_handle.await_count == 2  # info + status
    mock_ws.accept.assert_awaited_once()
    mock_room.add_user.assert_called_once()
    mock_room.remove_user.assert_called_once()
