import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.room.user import User
from app.services.room.user_handler import UserHandler
from app.services.room.room_storage import room_storage

router = APIRouter()

logger = logging.getLogger("app.websocket")


@router.websocket("/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()
    room = room_storage.get_room(room_id)
    if room is None:
        await websocket.close(code=4000, reason="Room not found")
        return

    connection_msg = await websocket.receive_json()
    if connection_msg.get("type") != "connect" or not connection_msg.get("name"):
        await websocket.close(code=4001, reason="Authentication is required")
        return

    user = User(connection_msg.get("name"), websocket)
    room.add_user(user)
    user_handler = UserHandler(user, room)
    await websocket.send_json({"type": "connect", "message": "success"})

    try:
        while True:
            data = await websocket.receive_json()
            await user_handler.handle(data)
    except WebSocketDisconnect:
        logger.info("The user disconnected")
    except Exception as e:
        logger.error(f"Error in WebSocket: {e}")
        await websocket.close(code=1011)  # Internal Error
    finally:
        room.remove_user(user)
