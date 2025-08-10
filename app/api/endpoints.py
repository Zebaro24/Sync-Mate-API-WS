from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/info")
async def info():
    return {
        "name": settings.app_name,
        "description": settings.description,
        "author": settings.author,
        "version": settings.version,
    }
