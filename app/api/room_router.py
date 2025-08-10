from fastapi import APIRouter

from app.services.room_storage import room_storage

router = APIRouter()


@router.post("/create")
async def create():
    room_id = room_storage.create_room()
    return {
        "room_id": room_id,
    }
