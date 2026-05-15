from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

from app.modules.room.dependencies import get_room_service
from app.modules.room.schemas import RoomCreate, RoomInternal, RoomResponse, RoomUpdate
from app.modules.room.service import RoomService

router = APIRouter(tags=["Rooms"])


@router.post("", response_model=RoomResponse, status_code=201)
async def create_room(
    data: RoomCreate,
    room_service: RoomService = Depends(get_room_service),
) -> RoomResponse:
    internal = RoomInternal(**data.model_dump())
    room = room_service.create_room(internal)
    return RoomResponse.from_room(room)


@router.get("", response_model=list[RoomResponse])
async def list_rooms(
    room_service: RoomService = Depends(get_room_service),
) -> list[RoomResponse]:
    return [RoomResponse.from_room(room) for room in room_service.rooms.values()]


@router.get("/{room_id}", response_model=RoomResponse)
async def get_room(
    room_id: str,
    room_service: RoomService = Depends(get_room_service),
) -> RoomResponse:
    room = room_service.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    return RoomResponse.from_room(room)


@router.patch("/{room_id}", response_model=RoomResponse)
async def update_room(
    room_id: str,
    data: RoomUpdate,
    room_service: RoomService = Depends(get_room_service),
) -> RoomResponse:
    room = room_service.update_room(room_id, data)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    return RoomResponse.from_room(room)


@router.delete("/{room_id}")
async def delete_room(
    room_id: str,
    room_service: RoomService = Depends(get_room_service),
) -> dict:
    room = room_service.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    if not room_service.delete_room(room_id):
        raise HTTPException(status_code=409, detail="Room has active users and cannot be deleted")
    return {"message": "Room deleted successfully"}


@router.get("/{room_id}/redirect")
async def redirect_to_video(
    room_id: str,
    room_service: RoomService = Depends(get_room_service),
) -> RedirectResponse:
    room = room_service.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    return RedirectResponse(url=room.video_url, status_code=307)
