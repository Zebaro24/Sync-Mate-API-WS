from app.schemas.room import RoomSchema
from app.services.room.room import Room


class RoomStorage:
    def __init__(self):
        self.storage = {}

    def create_room(self, room_schema: RoomSchema) -> Room:
        room = Room(**room_schema.model_dump())
        self.storage[room.room_id] = room
        return room

    def get_room(self, id_room) -> Room | None:
        return self.storage.get(id_room, None)

    def delete_room(self, id_room) -> bool:
        if self.storage[id_room].user_storage:
            return False
        del self.storage[id_room]
        return True


room_storage = RoomStorage()
