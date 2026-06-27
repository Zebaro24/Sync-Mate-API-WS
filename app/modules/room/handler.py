import asyncio
import logging
import math
from typing import Any

from app.modules.room.models import Room, User

logger = logging.getLogger(__name__)

# Разрешённый префикс источника видео — принимаем только Rezka.
ALLOWED_VIDEO_PREFIX = "https://rezka.ag/"


def _coerce_time(value: Any) -> float:
    """Безопасно приводит значение времени к неотрицательному конечному float."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(result):
        return 0.0
    return max(0.0, result)


class UserHandler:
    _VALID_ACTIONS = frozenset({"play", "pause", "status", "load", "set_video", "info"})

    def __init__(self, user: User, room: Room) -> None:
        self.user = user
        self.room = room

    async def _broadcast(self, data: dict) -> None:
        users = self.room.get_users_exc(self.user)
        await asyncio.gather(*(u.websocket.send_json(data) for u in users), return_exceptions=True)

    async def handle(self, data: dict) -> None:
        action = data.get("type")
        if action not in self._VALID_ACTIONS:
            return

        logger.debug("User '%s' room='%s' action=%s", self.user.name, self.room.name, action)

        if action == "info":
            self.user.info = {k: v for k, v in data.items() if k != "type"}
            # Логируем только ключи метаданных — значения могут быть произвольными.
            logger.debug(
                "info room='%s' user='%s' keys=%s",
                self.room.name,
                self.user.name,
                sorted(self.user.info.keys()),
            )
            return

        if action == "set_video":
            await self._handle_set_video(data)
            return

        self.user.current_time = _coerce_time(data.get("current_time"))
        self.user.downloaded_time = _coerce_time(data.get("downloaded_time"))
        # Длительность приходит со status; не затираем известное значение, если поля нет.
        if "duration" in data:
            self.user.duration = _coerce_time(data.get("duration"))

        if action == "status":
            await self._handle_status(data)
        elif action == "play":
            await self._handle_play(data)
        elif action == "pause":
            await self._handle_pause(data)
        elif action == "load":
            await self._handle_load(data)

    async def _handle_status(self, data: dict) -> None:
        logger.debug(
            "status room='%s' user='%s' current_time=%.2f downloaded_time=%.2f duration=%.2f is_loaded=%s is_paused=%s",
            self.room.name,
            self.user.name,
            self.user.current_time,
            self.user.downloaded_time,
            self.user.duration,
            self.room.is_loaded,
            self.room.is_paused,
        )
        if not self.room.is_loaded:
            is_loaded = await self.room.check_is_loaded(self.user)
            if is_loaded:
                if self.room.is_paused:
                    logger.debug("status room='%s' became loaded → remove_block_pause", self.room.name)
                    await self.room.remove_block_pause()
                else:
                    logger.debug("status room='%s' became loaded → play", self.room.name)
                    await self.room.play()

        broadcast = {k: v for k, v in data.items() if k != "current_time"}
        broadcast["type"] = "info"
        broadcast["name"] = self.user.name
        await self._broadcast(broadcast)
        logger.debug(
            "status room='%s' user='%s' → broadcast info to %d peer(s)",
            self.room.name,
            self.user.name,
            len(self.room.get_users_exc(self.user)),
        )

    async def _handle_play(self, data: dict) -> None:
        current_time = _coerce_time(data.get("current_time"))
        logger.debug(
            "play room='%s' user='%s' current_time=%.2f is_paused→False",
            self.room.name,
            self.user.name,
            current_time,
        )
        await self.room.seek(current_time, self.user)
        self.room.load(current_time)
        self.room.is_paused = False
        if await self.room.check_is_loaded(self.user):
            logger.debug("play room='%s' became loaded → play broadcast", self.room.name)
            await self.room.play()

    async def _handle_pause(self, data: dict) -> None:
        current_time = _coerce_time(data.get("current_time"))
        logger.debug(
            "pause room='%s' user='%s' current_time=%.2f is_paused→True",
            self.room.name,
            self.user.name,
            current_time,
        )
        # Сообщаем остальным позицию и собственно ставим на паузу — без второго
        # вызова другие клиенты продолжали бы воспроизведение.
        await self.room.seek(current_time, self.user)
        await self.room.pause(self.user)
        self.room.load(current_time)
        self.room.is_paused = True

    async def _handle_load(self, data: dict) -> None:
        """Клиент просит пересинхронизироваться с текущей позицией комнаты."""
        current_time = _coerce_time(data.get("current_time"))
        logger.debug("load room='%s' user='%s' current_time=%.2f", self.room.name, self.user.name, current_time)
        self.room.load(current_time)
        if await self.room.check_is_loaded(self.user):
            if self.room.is_paused:
                logger.debug("load room='%s' became loaded → remove_block_pause", self.room.name)
                await self.room.remove_block_pause()
            else:
                logger.debug("load room='%s' became loaded → play", self.room.name)
                await self.room.play()

    async def _handle_set_video(self, data: dict) -> None:
        """Сменить URL видео для всей комнаты."""
        video_url = data.get("video_url") or data.get("url")
        if not isinstance(video_url, str) or not video_url:
            logger.warning("set_video without valid video_url from user '%s'", self.user.name)
            return
        if not video_url.startswith(ALLOWED_VIDEO_PREFIX):
            logger.warning("set_video with non-rezka video_url from user '%s'", self.user.name)
            return
        current_time = _coerce_time(data.get("current_time"))
        logger.debug(
            "set_video room='%s' user='%s' video_url=%.80s current_time=%.2f",
            self.room.name,
            self.user.name,
            video_url,
            current_time,
        )
        await self.room.set_video_broadcast(video_url, current_time)
