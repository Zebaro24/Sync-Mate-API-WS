from fastapi import APIRouter

from app.api.rezka_router import router as rezka_router
from app.api.room_router import router as room_router
from app.config import settings

router = APIRouter()


router.include_router(room_router, prefix="/room")
router.include_router(rezka_router, prefix="/rezka")


@router.get("/info")
async def info():
    return {
        "name": settings.app_name,
        "description": settings.description,
        "author": settings.author,
        "version": settings.version,
    }
