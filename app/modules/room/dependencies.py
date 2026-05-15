from app.modules.room.service import RoomService

_room_service = RoomService()


def get_room_service() -> RoomService:
    return _room_service
