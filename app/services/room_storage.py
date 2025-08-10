from app.core.room import Room


class RoomStorage:
    def __init__(self):
        self.storage = {}

    def create_room(self):
        room = Room()
        self.storage[room.id] = room
        return room.id

    def get_room(self, id_room):
        return self.storage.get(id_room)


room_storage = RoomStorage()
