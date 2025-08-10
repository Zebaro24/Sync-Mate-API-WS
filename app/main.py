from fastapi import FastAPI

from app.api.endpoints import router as api_router
from app.config import settings
from app.ws.websocket import router as ws_router

app = FastAPI(
    title=settings.app_name,
    description=settings.description,
    version=settings.version,
    debug=settings.debug,
)

app.include_router(api_router, prefix="/api")
app.include_router(ws_router, prefix="/ws")
