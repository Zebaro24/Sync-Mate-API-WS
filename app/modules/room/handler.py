import asyncio
import logging

from app.modules.room.models import Room, User

logger = logging.getLogger(__name__)


class UserHandler:
    _VALID_ACTIONS = frozenset({"play", "pause", "status", "load", "set_video", "info"})

    def __init__(self, user: User, room: Room) -> None:
        self.user = user
        self.room = room

    async def _broadcast(self, data: dict) -> None:
        users = self.room.get_users_exc(self.user)
        await asyncio.gather(*(u.websocket.send_json(data) for u in users))

    async def handle(self, data: dict) -> None:
        action = data.get("type")
        if action not in self._VALID_ACTIONS:
            return

        logger.debug("User '%s' action=%s", self.user.name, action)

        if action == "info":
            self.user.info = {k: v for k, v in data.items() if k != "type"}
            return

        if action == "set_video":
            await self._handle_set_video(data)
            return

        self.user.current_time = float(data.get("current_time") or 0)
        self.user.downloaded_time = float(data.get("downloaded_time") or 0)

        if action == "status":
            await self._handle_status(data)
        elif action == "play":
            await self._handle_play(data)
        elif action == "pause":
            await self._handle_pause(data)
        elif action == "load":
            await self._handle_load(data)

    async def _handle_status(self, data: dict) -> None:
        if not self.room.is_loaded:
            is_loaded = await self.room.check_is_loaded(self.user)
            if is_loaded:
                if self.room.is_paused:
                    await self.room.remove_block_pause()
                else:
                    await self.room.play()

        broadcast = {k: v for k, v in data.items() if k != "current_time"}
        broadcast["type"] = "info"
        broadcast["name"] = self.user.name
        await self._broadcast(broadcast)

    async def _handle_play(self, data: dict) -> None:
        current_time = float(data.get("current_time") or 0)
        await self.room.seek(current_time, self.user)
        self.room.load(current_time)
        self.room.is_paused = False
        if await self.room.check_is_loaded(self.user):
            await self.room.play()

    async def _handle_pause(self, data: dict) -> None:
        current_time = float(data.get("current_time") or 0)
        # Сообщаем остальным позицию и собственно ставим на паузу — без второго
        # вызова другие клиенты продолжали бы воспроизведение.
        await self.room.seek(current_time, self.user)
        await self.room.pause(self.user)
        self.room.load(current_time)
        self.room.is_paused = True

    async def _handle_load(self, data: dict) -> None:
        """Клиент просит пересинхронизироваться с текущей позицией комнаты."""
        current_time = float(data.get("current_time") or 0)
        self.room.load(current_time)
        if await self.room.check_is_loaded(self.user):
            if self.room.is_paused:
                await self.room.remove_block_pause()
            else:
                await self.room.play()

    async def _handle_set_video(self, data: dict) -> None:
        """Сменить URL видео для всей комнаты."""
        video_url = data.get("video_url") or data.get("url")
        if not isinstance(video_url, str) or not video_url:
            logger.warning("set_video without valid video_url from user '%s'", self.user.name)
            return
        current_time = float(data.get("current_time") or 0)
        await self.room.set_video_broadcast(video_url, current_time)
