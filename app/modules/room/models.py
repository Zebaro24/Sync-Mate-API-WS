import asyncio
import logging
from typing import Any
from uuid import uuid4

from fastapi import WebSocket

from app.config import settings

logger = logging.getLogger(__name__)


class User:
    def __init__(self, name: str, websocket: WebSocket) -> None:
        self.user_id: str = str(uuid4())
        self.name = name
        self.websocket = websocket
        self.current_time: float = 0.0
        self.downloaded_time: float = 0.0
        self.info: dict[str, Any] = {}
        logger.info("User '%s' connected from %s", name, websocket.client)


class Room:
    def __init__(
        self,
        room_id: str,
        name: str,
        video_url: str,
        current_time: float,
        created_at,
    ) -> None:
        self.room_id = room_id
        self.name = name
        self.video_url = video_url
        self.current_time: float = current_time
        self.is_paused = False
        self.is_loaded = False
        self.user_storage: list[User] = []
        self.created_at = created_at
        # Сериализует изменения состояния и broadcast, чтобы избежать гонок
        # между check_is_loaded / add_user / remove_user при конкурентных WS.
        self._lock = asyncio.Lock()

    async def add_user(self, user: User) -> None:
        async with self._lock:
            self.user_storage.append(user)

    async def remove_user(self, user: User) -> None:
        async with self._lock:
            if user in self.user_storage:
                self.user_storage.remove(user)

    def set_video(self, video_url: str, current_time: float = 0.0) -> None:
        self.video_url = video_url
        self.current_time = current_time
        self.is_loaded = False
        self.is_paused = False

    def get_users_exc(self, exception_user: "User | None" = None) -> "list[User]":
        return [u for u in self.user_storage if u != exception_user]

    def load(self, current_time: float) -> None:
        self.current_time = current_time
        self.is_loaded = False

    async def check_is_loaded(self, check_user: "User") -> bool:
        async with self._lock:
            # Корректируем всех, у кого позиция расходится с комнатной — иначе
            # один отстающий пользователь блокирует запуск воспроизведения навсегда.
            laggards = [u for u in self.user_storage if u.current_time != self.current_time]
            if laggards:
                await asyncio.gather(
                    *(u.websocket.send_json({"type": "seek", "current_time": self.current_time}) for u in laggards)
                )

            all_ready = len(self.user_storage) > 0 and all(
                u.current_time == self.current_time and u.downloaded_time >= settings.REQUIRED_DOWNLOAD_TIME
                for u in self.user_storage
            )
            if all_ready:
                self.is_loaded = True
            return all_ready

    async def play(self) -> None:
        logger.info("Room '%s' → play", self.name)
        await asyncio.gather(*(u.websocket.send_json({"type": "play"}) for u in self.user_storage))

    async def pause(self, exception_user: "User | None" = None) -> None:
        logger.info("Room '%s' → pause", self.name)
        users = self.get_users_exc(exception_user)
        await asyncio.gather(*(u.websocket.send_json({"type": "pause"}) for u in users))

    async def seek(
        self,
        current_time: float,
        exception_user: "User | None" = None,
        user: "User | None" = None,
    ) -> None:
        logger.debug("Room '%s' → seek %.2f", self.name, current_time)
        if user:
            await user.websocket.send_json({"type": "seek", "current_time": current_time})
            return
        users = self.get_users_exc(exception_user)
        await asyncio.gather(*(u.websocket.send_json({"type": "seek", "current_time": current_time}) for u in users))

    async def set_video_broadcast(self, video_url: str, current_time: float = 0.0) -> None:
        """Обновить URL видео в комнате и оповестить всех участников."""
        self.set_video(video_url, current_time)
        logger.info("Room '%s' → set_video %s", self.name, video_url)
        await asyncio.gather(
            *(
                u.websocket.send_json({"type": "set_video", "video_url": video_url, "current_time": current_time})
                for u in self.user_storage
            )
        )

    async def remove_block_pause(self) -> None:
        await asyncio.gather(*(u.websocket.send_json({"type": "remove_block_pause"}) for u in self.user_storage))

    def __repr__(self) -> str:
        return f"<Room name={self.name!r} id={self.room_id!r} users={len(self.user_storage)}>"
