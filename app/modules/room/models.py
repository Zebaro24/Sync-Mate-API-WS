import asyncio
import logging
import time
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
        self.duration: float = 0.0
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
        # Момент (monotonic), с которого комната ждёт готовности всех участников.
        # Сбрасывается каждый раз, когда is_loaded снова становится False.
        self._wait_started_at: float = time.monotonic()
        # Сериализует изменения состояния и broadcast, чтобы избежать гонок
        # между check_is_loaded / add_user / remove_user при конкурентных WS.
        self._lock = asyncio.Lock()

    async def add_user(self, user: User) -> None:
        async with self._lock:
            self.user_storage.append(user)
            # Сбрасываем готовность: поздний участник обязан пересинхронизироваться.
            self.is_loaded = False
            self._wait_started_at = time.monotonic()

    async def remove_user(self, user: User) -> None:
        recipients: list[User] = []
        message: dict[str, Any] = {}
        async with self._lock:
            if user in self.user_storage:
                self.user_storage.remove(user)
            # Уход «тормозящего» может сделать оставшихся готовыми — пересчитываем
            # под локом. Иначе готовые залипнут: свой status они уже отправили
            # и повторно его не пришлют, так что некому будет дёрнуть запуск.
            if not self.is_loaded and self._all_ready_locked():
                self.is_loaded = True
                recipients = list(self.user_storage)
                message = {"type": "remove_block_pause"} if self.is_paused else {"type": "play"}
        # Сетевой I/O — после выхода из лока.
        if recipients:
            await asyncio.gather(
                *(u.websocket.send_json(message) for u in recipients),
                return_exceptions=True,
            )

    def set_video(self, video_url: str, current_time: float = 0.0) -> None:
        self.video_url = video_url
        self.current_time = current_time
        self.is_loaded = False
        self.is_paused = False
        self._wait_started_at = time.monotonic()
        # Сбрасываем состояние участников: после смены видео старые позиция и буфер
        # не должны давать ложную готовность, если клиент не перезагрузил страницу.
        for u in self.user_storage:
            u.downloaded_time = 0.0
            u.current_time = current_time

    def get_users_exc(self, exception_user: "User | None" = None) -> "list[User]":
        return [u for u in self.user_storage if u != exception_user]

    def load(self, current_time: float) -> None:
        self.current_time = current_time
        self.is_loaded = False
        self._wait_started_at = time.monotonic()

    def _buffer_needed(self, user: "User") -> float:
        """Сколько секунд буфера нужно пользователю: ближе к концу ролика остаток меньше."""
        if user.duration > 0:
            return min(float(settings.REQUIRED_DOWNLOAD_TIME), max(0.0, user.duration - user.current_time))
        return float(settings.REQUIRED_DOWNLOAD_TIME)

    def _user_ready_locked(self, user: "User") -> bool:
        """Готов ли один участник: позиция в допуске и набран нужный буфер.

        Только под self._lock — без I/O и без повторного захвата лока (он не реентрантный).
        """
        tol = settings.SYNC_TOLERANCE
        return (
            abs(user.current_time - self.current_time) <= tol
            and user.downloaded_time >= self._buffer_needed(user) - tol
        )

    def _all_ready_locked(self) -> bool:
        """Готовы ли все участники. Только под self._lock (без I/O, лок не реентрантный)."""
        return len(self.user_storage) > 0 and all(self._user_ready_locked(u) for u in self.user_storage)

    async def check_is_loaded(self, check_user: "User", now: float | None = None) -> bool:
        """Пересчитать готовность комнаты.

        Под локом — только вычисления и мутация состояния; весь send_json выполняется
        ПОСЛЕ выхода из лока. Возвращает True, только если ИМЕННО этот вызов перевёл
        комнату в is_loaded — защита от двойного play при гонке параллельных status.

        Если ожидание длится дольше settings.READY_TIMEOUT и готовы не все —
        стартуем по уже готовым (is_loaded=True, play/remove_block_pause только им),
        чтобы один медленный клиент не морозил остальных навсегда; отстающим при этом
        по-прежнему уходит seek.
        """
        if now is None:
            now = time.monotonic()

        timeout_recipients: list[User] = []
        timeout_message: dict[str, Any] = {}
        async with self._lock:
            tol = settings.SYNC_TOLERANCE
            target = self.current_time
            # Кого нужно подтянуть seek'ом — позиция расходится с комнатной больше допуска.
            laggards = [u for u in self.user_storage if abs(u.current_time - target) > tol]
            all_ready = self._all_ready_locked()
            # True только при переходе False→True, чтобы не разослать play дважды.
            became_loaded = all_ready and not self.is_loaded

            timed_out = False
            if not all_ready and not self.is_loaded and self.user_storage:
                ready = [u for u in self.user_storage if self._user_ready_locked(u)]
                if ready and (now - self._wait_started_at) > settings.READY_TIMEOUT:
                    timed_out = True
                    timeout_recipients = ready
                    timeout_message = {"type": "remove_block_pause"} if self.is_paused else {"type": "play"}

            if all_ready or timed_out:
                self.is_loaded = True

        # Сетевой I/O — вне лока (send_json не должен держать lock).
        if laggards:
            await asyncio.gather(
                *(u.websocket.send_json({"type": "seek", "current_time": target}) for u in laggards),
                return_exceptions=True,
            )
        if timeout_recipients:
            await asyncio.gather(
                *(u.websocket.send_json(timeout_message) for u in timeout_recipients),
                return_exceptions=True,
            )
        return became_loaded

    async def play(self) -> None:
        logger.info("Room '%s' → play", self.name)
        await asyncio.gather(
            *(u.websocket.send_json({"type": "play"}) for u in self.user_storage), return_exceptions=True
        )

    async def pause(self, exception_user: "User | None" = None) -> None:
        logger.info("Room '%s' → pause", self.name)
        users = self.get_users_exc(exception_user)
        await asyncio.gather(*(u.websocket.send_json({"type": "pause"}) for u in users), return_exceptions=True)

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
        await asyncio.gather(
            *(u.websocket.send_json({"type": "seek", "current_time": current_time}) for u in users),
            return_exceptions=True,
        )

    async def set_video_broadcast(self, video_url: str, current_time: float = 0.0) -> None:
        """Обновить URL видео в комнате и оповестить всех участников."""
        self.set_video(video_url, current_time)
        logger.info("Room '%s' → set_video %s", self.name, video_url)
        await asyncio.gather(
            *(
                u.websocket.send_json({"type": "set_video", "video_url": video_url, "current_time": current_time})
                for u in self.user_storage
            ),
            return_exceptions=True,
        )

    async def remove_block_pause(self) -> None:
        await asyncio.gather(
            *(u.websocket.send_json({"type": "remove_block_pause"}) for u in self.user_storage), return_exceptions=True
        )

    def __repr__(self) -> str:
        return f"<Room name={self.name!r} id={self.room_id!r} users={len(self.user_storage)}>"
