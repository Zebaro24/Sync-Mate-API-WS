from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from app.schemas.room import RoomRequest, RoomResponse, RoomSchema, RoomUpdate
from app.services.room.room_storage import room_storage

router = APIRouter()


@router.post("", response_model=RoomResponse, tags=["Room"])
async def create(data: RoomRequest):
    room_schema = RoomSchema(**data.model_dump())
    room = room_storage.create_room(room_schema)
    return RoomResponse.from_room(room)


@router.get("", response_model=list[RoomResponse], tags=["Room"])
async def get():
    return [RoomResponse.from_room(room) for room in room_storage.storage.values()]


@router.get("/{room_id}", response_model=RoomResponse, tags=["Room"])
async def get_by_id(room_id: str):
    room = room_storage.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return RoomResponse.from_room(room)


@router.patch("/{room_id}", response_model=RoomResponse, tags=["Room"])
async def update(room_id: str, data: RoomUpdate):
    room = room_storage.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(room, key, value)

    return RoomResponse.from_room(room)


@router.delete("/{room_id}", tags=["Room"])
async def delete(room_id: str):
    room = room_storage.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    res = room_storage.delete_room(room_id)
    if not res:
        raise HTTPException(status_code=400, detail="Room cannot be deleted")
    return {"message": "Room deleted successfully"}


@router.get("/{room_id}/redirect", tags=["Room"])
async def redirect(room_id: str):
    room = room_storage.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return RedirectResponse(url=room.video_url, status_code=307)
