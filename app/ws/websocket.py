from fastapi import WebSocket, WebSocketDisconnect
import logging

logger = logging.getLogger("app.websocket")


async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_text("Welcome to WebSocket!")
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"You said: {data}")
    except WebSocketDisconnect:
        logger.info("The client disconnected")
    except Exception as e:
        logger.error(f"Error in WebSocket: {e}")
        await websocket.close(code=1011)  # Internal Error
