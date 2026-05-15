from fastapi import APIRouter

from app.config import settings
from app.modules.rezka.router import router as rezka_router
from app.modules.room.router import router as room_router

router = APIRouter()

router.include_router(room_router, prefix="/rooms")
router.include_router(rezka_router, prefix="/rezka")


@router.get("/info", tags=["General"])
async def info() -> dict:
    return {
        "name": settings.app_name,
        "description": settings.description,
        "author": settings.author,
        "version": settings.version,
    }
