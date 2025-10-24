import asyncio
from typing import List

from app.config import settings
from app.services.room.user import User


class Room:
    def __init__(self, room_id: str, name: str, video_url: str, current_time: int, created_at):
        self.room_id: str = room_id
        self.name: str = name

        self.is_paused = False
        self.is_loaded = False

        self.video_url: str = video_url
        self.current_time: int = current_time

        self.user_storage: List[User] = []

        self.created_at = created_at

    def add_user(self, user: User):
        self.user_storage.append(user)

    def remove_user(self, user: User):
        self.user_storage.remove(user)

    def set_video(self, video_url: str, current_time: int = 0):
        self.video_url = video_url
        self.current_time = current_time

    def get_users_exc(self, exception_user: User | None = None):
        return [user for user in self.user_storage if user != exception_user]

    def load(self, current_time):
        self.current_time = current_time
        self.is_loaded = False

    async def check_is_loaded(self, check_user):
        res_is_loaded = True

        if check_user.current_time != self.current_time:
            await self.seek(self.current_time, user=check_user)

        for user in self.user_storage:
            if user.current_time != self.current_time:
                res_is_loaded = False
            elif user.downloaded_time < settings.REQUIRED_DOWNLOAD_TIME:
                res_is_loaded = False

        if res_is_loaded:
            self.is_loaded = True
            return True
        return False

    async def play(self):
        print(f"Room {self.name} is <playing>")
        await asyncio.gather(*[user.websocket.send_json({"type": "play"}) for user in self.user_storage])

    async def pause(self, exception_user=None):
        print(f"Room {self.name} is <pausing>")
        users = self.get_users_exc(exception_user)
        await asyncio.gather(*[user.websocket.send_json({"type": "pause"}) for user in users])

    async def seek(self, current_time, exception_user=None, user=None):
        print(f"Room {self.name} is <seeking>")
        if user:
            await user.websocket.send_json({"type": "seek", "current_time": current_time})
            return
        users = self.get_users_exc(exception_user)
        await asyncio.gather(
            *[user.websocket.send_json({"type": "seek", "current_time": current_time}) for user in users]
        )

    async def remove_block_pause(self):
        await asyncio.gather(*[user.websocket.send_json({"type": "remove_block_pause"}) for user in self.user_storage])

    def __str__(self):
        return f"<Room {self.name}: id={self.room_id} users={[user.websocket.client for user in self.user_storage]}>"
