from app.modules.room.models import Room
from app.modules.room.schemas import RoomInternal, RoomUpdate


class RoomService:
    def __init__(self) -> None:
        self._storage: dict[str, Room] = {}

    @property
    def rooms(self) -> dict[str, Room]:
        return self._storage

    def create_room(self, schema: RoomInternal) -> Room:
        room = Room(**schema.model_dump())
        self._storage[room.room_id] = room
        return room

    def get_room(self, room_id: str) -> Room | None:
        return self._storage.get(room_id)

    def update_room(self, room_id: str, update: RoomUpdate) -> Room | None:
        room = self.get_room(room_id)
        if room is None:
            return None
        for field, value in update.model_dump(exclude_unset=True).items():
            setattr(room, field, value)
        return room

    def delete_room(self, room_id: str) -> bool:
        room = self.get_room(room_id)
        if room is None or room.user_storage:
            return False
        del self._storage[room_id]
        return True
