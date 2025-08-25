import asyncio

from app.services.room.room import Room
from app.services.room.user import User


class UserHandler:
    ACTION_TYPES = ["play", "pause", "status", "load", "set_video"]

    def __init__(self, user: User, room: Room):
        self.user = user
        self.room = room

    async def send_to_room(self, data: dict):
        users = self.room.get_users_exc(self.user)
        await asyncio.gather(*(user.websocket.send_json(data) for user in users))

    async def handle(self, data: dict):
        if data.get("type") not in self.ACTION_TYPES:
            return
        print(f"User {self.user.name} sent {data}")

        self.user.current_time = data.get("current_time")
        self.user.downloaded_time = data.get("downloaded_time")

        if data.get("type") == "status":
            if not self.room.is_loaded:
                is_loaded = await self.room.check_is_loaded(self.user)
                if is_loaded:
                    if self.room.is_paused:
                        await self.room.remove_block_pause()
                    else:
                        await self.room.play()

            data["type"] = "info"
            del data["current_time"]
            await self.send_to_room(data)
            return

        # Request play, I need to confirm
        if data.get("type") == "play":
            await self.room.seek(data.get("current_time"), self.user)
            self.room.load(data.get("current_time"))

            if await self.room.check_is_loaded(self.user):
                await self.room.play()
            self.room.is_paused = False

        if data.get("type") == "pause":
            await self.room.seek(data.get("current_time"), self.user)
            self.room.load(data.get("current_time"))
            self.room.is_paused = True
