import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.modules.room.dependencies import get_room_service
from app.modules.room.handler import UserHandler
from app.modules.room.models import User
from app.modules.room.service import RoomService
from app.ws.schemas import ConnectMessage

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    room_service: RoomService = Depends(get_room_service),
) -> None:
    await websocket.accept()

    room = room_service.get_room(room_id)
    if room is None:
        await websocket.close(code=4000, reason="Room not found")
        return

    try:
        raw = await websocket.receive_json()
        connect = ConnectMessage.model_validate(raw)
    except (ValidationError, Exception):
        await websocket.close(code=4001, reason="Authentication is required")
        return

    user = User(connect.name, websocket)
    await room.add_user(user)
    handler = UserHandler(user, room)
    await websocket.send_json({"type": "connect", "id": user.user_id})

    try:
        while True:
            data = await websocket.receive_json()
            await handler.handle(data)
    except WebSocketDisconnect:
        logger.info("User '%s' disconnected from room '%s'", user.name, room_id)
    except Exception as e:
        logger.error("WebSocket error for user '%s': %s", user.name, e)
        try:
            await websocket.close(code=1011)
        except Exception as close_err:
            # Сокет уже мог быть закрыт клиентом — это нормально, просто логируем.
            logger.debug("Failed to close WebSocket cleanly: %s", close_err)
    finally:
        await room.remove_user(user)
