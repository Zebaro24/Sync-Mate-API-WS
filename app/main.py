from fastapi import FastAPI, WebSocket

from app.api.endpoints import router as api_router
from app.config import settings
from app.ws.websocket import websocket_endpoint

app = FastAPI(
    title=settings.app_name,
    description=settings.description,
    version=settings.version,
    debug=settings.debug,
)

app.include_router(api_router)  # подключаем REST API


@app.websocket("/ws")  # подключаем WebSocket вручную
async def websocket_route(websocket: WebSocket):
    await websocket_endpoint(websocket)
