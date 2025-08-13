import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.client_handler import ClientHandler
from app.services.room.room_storage import room_storage

router = APIRouter()

logger = logging.getLogger("app.websocket")


@router.websocket("/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    room = room_storage.get_room(room_id)
    if room is None:
        await websocket.close(code=1008)  # policy violation
        return

    room.add_client(websocket)
    client_handler = ClientHandler(room, websocket)

    await websocket.accept()
    await websocket.send_text("Connection success!")
    try:
        while True:
            data = await websocket.receive_json()
            await client_handler.handle(data)
    except WebSocketDisconnect:
        logger.info("The client disconnected")
    except Exception as e:
        logger.error(f"Error in WebSocket: {e}")
        await websocket.close(code=1011)  # Internal Error
    finally:
        room.remove_client(websocket)
