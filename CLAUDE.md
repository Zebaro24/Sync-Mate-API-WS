# CLAUDE.md — Sync-Mate-API-WS

Гид для Claude по бэкенд-части. Полное описание архитектуры — в [../DOCUMENTATION.md](../DOCUMENTATION.md).

## Стек

- Python 3.11+ (Docker — 3.13), Poetry
- FastAPI + WebSockets (uvicorn[standard])
- httpx (AsyncClient) — HTTP-клиент к rezka.ag
- pydantic-settings — конфигурация из `.env`
- pytest + pytest-asyncio + pytest-mock — тесты

## Запуск

```bash
poetry install
poetry run uvicorn app.main:app --reload         # http://127.0.0.1:8000
poetry run pytest                                # 54 теста
```

Docker: `make up` / `make down`. Локально с туннелем: `make run`.

## Архитектура слоёв

```
HTTP/WS → main.py
    ├─ /api → api/router.py
    │       ├─ /rooms      → modules/room/router.py     (REST CRUD)
    │       └─ /rezka      → modules/rezka/router.py    (REST search/info/source)
    └─ /ws/{room_id} → ws/router.py
            └─ UserHandler → modules/room/handler.py    (обработка WS-сообщений)
                  ├─ Room  → modules/room/models.py     (доменная модель + asyncio.Lock)
                  └─ RoomService → modules/room/service.py (in-memory dict)
```

## Контракт WS-протокола

Полный список сообщений — в `DOCUMENTATION.md` §2.5. Запомните минимум:

- Первое сообщение клиента **обязательно** `{"type":"connect","name":"..."}` — иначе close 4001.
- Сервер отвечает `{"type":"connect","id":"<uuid>"}` и переходит в основной цикл.
- Действия (`play`, `pause`, `status`, `load`, `set_video`) обновляют `user.current_time` и `user.downloaded_time` через `UserHandler`.
- `info` — произвольные метаданные пользователя, сохраняются в `user.info`.

Любая правка `_VALID_ACTIONS` обязана идти вместе с реализацией обработчика — иначе действие будет «молчаливо принято» без эффекта (исторический баг).

## Race conditions — что важно

`Room._lock: asyncio.Lock` сериализует:

- `add_user` / `remove_user`
- `check_is_loaded` (вычитка `user_storage` + проверка готовности)

**Не вызывайте** `room.play()` / `room.seek()` / `room.pause()` изнутри блока `async with self._lock:` — внутри уже идёт async send_json, и вы получите рекурсивную блокировку при попытке другого `_handle_*` параллельно. Если нужно — выходите из локa перед рассылкой.

## Rezka — особенности

- Все методы `RezkaService` / `RezkaStream` **async**. Из роутеров обязательно `await service.method(...)`.
- HTTP-ошибки rezka.ag пробрасываются как `httpx.HTTPError` — это превращается в 500. Не глушите без причины.
- Парсинг сезонов в `get_series_source` устойчив к локализации (regex по числу), но всё ещё хрупкий — если Rezka сменит HTML-структуру, ожидайте поломок.

## Тесты

- `tests/conftest.py` — автоочистка глобального `RoomService._storage` между тестами.
- `pytest.mark.asyncio` ставится **явно** на каждый async-тест (нет `asyncio_mode = "auto"`).
- Mock httpx — через `mocker.patch.object(service, "post"|"get", AsyncMock(return_value=...))`.
- WS-тесты используют `SimpleNamespace` с `mocker.AsyncMock()` для `add_user`/`remove_user`.

## Конфигурация

- `.env` — в `.gitignore`, но в репозитории присутствует с реальным `CLOUDFLARE_TUNNEL_TOKEN`. Не редактируйте без необходимости и не коммитьте изменения.
- `Settings` (Pydantic) читает `.env`. `PROXIES_LIST` принимает CSV-строку и сам распарсит в список.

## Что НЕ делать

- Не возвращайте sync httpx — мы специально перевели на AsyncClient.
- Не добавляйте обработчики в `_VALID_ACTIONS` без соответствующего `_handle_*` метода.
- Не убирайте `await room.remove_user(user)` из `finally:` в WS-роутере — иначе утечка.
- Не пишите `room.user_storage.remove(user)` — используйте `await room.remove_user(user)` (идемпотентный, под локoм).
