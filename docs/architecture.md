# Архитектура бэкенда Sync-Mate-API-WS

Полный справочник по устройству FastAPI + WebSocket-сервера: слоистая модель, потоки REST и WS-запросов, фабрика приложения, доменная модель комнаты, правила сериализации под `asyncio.Lock` и принудительные архитектурные инварианты.

> Документ описывает **реальность кода** на момент написания. Корневой `DOCUMENTATION.md` частично устарел (особенно раздел про деплой) — при расхождениях доверяйте этому файлу и исходникам, а не старой документации.

---

## 1. Слоистая модель

Зависимости направлены строго сверху вниз. Нижние слои **не знают** о верхних; два модуля внутри `app/modules/` изолированы друг от друга.

```
                ┌─────────────────────────────────────────────┐
   HTTP / WS →  │  app/main.py   (фабрика FastAPI, logging, CORS) │
                └───────────────┬─────────────────────────────┘
                                │ include_router
                ┌───────────────┴───────────────┐
                │                                │
        prefix="/api"                      prefix="/ws"
        app/api/router.py                  app/ws/router.py
                │                                │
     ┌──────────┴──────────┐                     │ UserHandler
     │                     │                     ▼
 /rooms               /rezka          app/modules/room/handler.py
 room/router.py       rezka/router.py             │
     │                     │           ┌──────────┴──────────┐
     ▼                     ▼           ▼                     ▼
 room/service.py      rezka/service.py  room/models.py    room/service.py
 room/schemas.py      rezka/_base.py    (Room / User      (RoomService,
 room/models.py       rezka/_decoder.py  + asyncio.Lock)   in-memory dict)
     │                     │
     └──────────┬──────────┘
                ▼
          app/config.py   (Settings, pydantic-settings)
```

| Слой | Каталог | Роль | Кому можно импортировать |
|---|---|---|---|
| Точка входа | `app/main.py` | Сборка приложения, логирование, CORS, монтирование роутеров | всё |
| HTTP-роутинг | `app/api/router.py` | Агрегирует REST-роутеры модулей, отдаёт `/api/info` | модули, config |
| WS-роутинг | `app/ws/router.py` | WebSocket-эндпоинт, handshake, главный цикл | `modules/room`, `ws/schemas` |
| Модули | `app/modules/{room,rezka}` | Бизнес-логика, домен, доступ к данным | только `app.config` и собственный модуль |
| Конфигурация | `app/config.py` | `Settings` из `.env` | ничего из `app` (лист дерева) |

Ключевое правило: **`app/modules/**` не импортирует `app.api`, `app.ws`, `app.main`**, а `modules/rezka` и `modules/room` не импортируют друг друга. Это автоматически проверяется (см. §11).

---

## 2. Фабрика приложения и логирование (`app/main.py`)

Файл короткий (63 строки) и выполняет четыре задачи по порядку.

### 2.1. Конфигурация логирования (`app/main.py:10-44`)

`LOGGING_CONFIG` — словарь в формате `logging.config.dictConfig`, применяется на уровне модуля **до** создания приложения (`app/main.py:44`).

| Элемент | Значение | Примечание |
|---|---|---|
| `formatters.default.format` | `%(asctime)s \| %(levelname)-8s \| %(name)s - %(message)s` | единый формат для всех хендлеров |
| `formatters.default.datefmt` | `%Y-%m-%d %H:%M:%S` | |
| `handlers.console` | `logging.StreamHandler` с форматтером `default` | вывод в stderr/stdout |
| `loggers.app` | level `DEBUG` если `settings.debug`, иначе `INFO`; `propagate=False` | все модули логируют через `logging.getLogger(__name__)`, имена начинаются с `app.` |
| `loggers.uvicorn.access` / `uvicorn.error` | level `INFO`, `propagate=False` | перехватывают логи uvicorn в общий формат |
| `disable_existing_loggers` | `False` | сторонние логгеры (httpx и т.п.) не глушатся |

`propagate=False` у `app` критичен: без него сообщения дублировались бы корневым логгером uvicorn. Уровень логгера `app` — единственное, на что влияет `settings.debug` в логировании.

### 2.2. Создание приложения (`app/main.py:46-51`)

```python
app = FastAPI(
    title=settings.app_name,
    description=settings.description,
    version=settings.version,
    debug=settings.debug,
)
```

Все метаданные берутся из `Settings` — см. §3. `debug=settings.debug` включает подробные трейсбэки FastAPI.

### 2.3. CORS (`app/main.py`)

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
```

Origin открыт (расширение работает с произвольных страниц Rezka и из `chrome-extension://…`, конкретный origin заранее неизвестен), но **`allow_credentials=False`**: куки/credentials API не использует, а связка `*` + credentials позволяла бы чужому сайту дёргать API в контексте пользователя. Сужать origin списком нельзя — id расширения и origin страницы не фиксированы. См. BE-6 в бэклоге: привязка PATCH/DELETE к создателю (owner-токен) — отдельная задача.

### 2.4. Монтирование роутеров (`app/main.py:61-62`)

```python
app.include_router(api_router, prefix="/api")   # REST
app.include_router(ws_router, prefix="/ws")     # WebSocket
```

Итоговые префиксы путей:

| Источник | Базовый префикс | Полный путь |
|---|---|---|
| `app/api/router.py` → `room_router` | `/api/rooms` | `/api/rooms...` |
| `app/api/router.py` → `rezka_router` | `/api/rezka` | `/api/rezka/...` |
| `app/api/router.py` → `info` | `/api` | `/api/info` |
| `app/ws/router.py` | `/ws/{room_id}` | `/ws/{room_id}` |

---

## 3. Конфигурация (`app/config.py`)

`Settings(BaseSettings)` из `pydantic-settings`, читает `.env` (`model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")`, `app/config.py:23`). Глобальный синглтон `settings = Settings()` создаётся на уровне модуля (`app/config.py:31`).

| Поле | Тип | Дефолт | Назначение |
|---|---|---|---|
| `app_name` | `str` | `"Sync-Mate-API-WS"` | `title` приложения и поле `/api/info` |
| `description` | `str` | длинная строка | `description` приложения |
| `author` | `str` | `"Zebaro (zebaro.dev)"` | поле `/api/info` |
| `version` | `str` | `"0.1.1"` | `version` приложения и `/api/info` |
| `debug` | `bool` | `False` | уровень логов + режим FastAPI |
| `REQUIRED_DOWNLOAD_TIME` | `int` | `15` | сколько секунд буфера обязан иметь каждый клиент, чтобы комната «загрузилась» (см. §8.3) |
| `REZKA_URL` | `str` | `"https://rezka.ag"` | базовый URL для `RezkaBase` |
| `PROXIES_LIST` | `list \| str \| None` | `None` | список прокси для запросов к Rezka |

`PROXIES_LIST` принимает CSV-строку из переменной окружения и в `__init__` (`app/config.py:25-28`) сам разбивает её по запятым в `list`. Это обходит ограничение pydantic на парсинг сложных типов из плоских строк env.

> `version` в `Settings` (`0.1.1`) и `version` в `pyproject.toml` (`0.1.0`) расходятся — отображаемая в API версия берётся из `Settings`.

**Имена переменных окружения** (значения — секреты, не читать):

- Приложение: `DEBUG`, `REQUIRED_DOWNLOAD_TIME`, `REZKA_URL`, `PROXIES_LIST` (плюс при желании `APP_NAME`, `DESCRIPTION`, `AUTHOR`, `VERSION`).
- Локальный запуск/туннель (`Makefile`): `PORT`, `CLOUDFLARE_TUNNEL_TOKEN`.
- Docker / деплой: `SERVER_PORT` (см. `docker-compose.yml`), а в `cd.yml` — секреты `SERVER_HOST`, `SERVER_USER`, `SSH_PRIVATE_KEY`, `GITHUB_TOKEN` и переменная `vars.SERVER_PORT`.

---

## 4. HTTP-слой (REST API)

### 4.1. Агрегатор (`app/api/router.py`)

`APIRouter`, подключающий два модульных роутера и один свой эндпоинт:

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/api/info` | метаданные сервиса (`name`, `description`, `author`, `version`) из `settings` |
| — | `/api/rooms` → `room_router` | CRUD комнат |
| — | `/api/rezka` → `rezka_router` | поиск/инфо/источники Rezka |

### 4.2. Эндпоинты комнат (`app/modules/room/router.py`)

`router = APIRouter(tags=["Rooms"])`. Все хендлеры — `async def`, зависимость `room_service: RoomService = Depends(get_room_service)`.

| Метод | Путь | Хендлер:line | Поведение / коды |
|---|---|---|---|
| `POST` | `/api/rooms` | `create_room` `:11` | `201`, тело `RoomCreate` → `RoomInternal` → `RoomService.create_room`; ответ `RoomResponse` |
| `GET` | `/api/rooms` | `list_rooms` `:21` | список всех комнат `list[RoomResponse]` — **только в debug**; в проде `404` (анти-энумерация) |
| `GET` | `/api/rooms/{room_id}` | `get_room` `:28` | `404` если нет; иначе `RoomResponse` |
| `PATCH` | `/api/rooms/{room_id}` | `update_room` `:39` | частичное обновление через `RoomUpdate`; `404` если нет |
| `DELETE` | `/api/rooms/{room_id}` | `delete_room` `:51` | `404` если нет; `409` если в комнате есть пользователи; иначе `{"message": ...}` |
| `GET` | `/api/rooms/{room_id}/redirect` | `redirect_to_video` `:64` | `404` если нет; иначе `RedirectResponse(room.video_url, 307)` |

**Гоча `DELETE`:** удаление двухступенчатое. Сначала `get_room` (для различения `404`), затем `room_service.delete_room`, который вернёт `False`, если `room.user_storage` непустой → `409`. То есть нельзя удалить комнату, в которой кто-то сидит по WS.

### 4.3. Схемы комнат (`app/modules/room/schemas.py`)

Иерархия Pydantic-моделей, реализующая разделение «вход / внутреннее / выход»:

| Модель | Базируется на | Поля / особенности |
|---|---|---|
| `RoomCreate` | `BaseModel` | `name`, `video_url`, `current_time=0.0` — то, что присылает клиент |
| `RoomUpdate` | `BaseModel` | те же поля, все `Optional[None]` — для `PATCH` с `exclude_unset` |
| `RoomInternal` | `RoomCreate` | + `room_id` (`uuid4` по умолчанию), `created_at` (`datetime.now(timezone.utc)`) |
| `UserResponse` | `BaseModel` | `user_id`, `name`, `current_time`, `downloaded_time`, `info` |
| `RoomResponse` | `RoomInternal` | + `status` (`"waiting"` по умолчанию), `users`, вычисляемое `link` |

`RoomResponse.link` (`@computed_field`, `:37-40`) — `"/api/rooms/{room_id}/redirect"`.

`RoomResponse.from_room` (`:42-68`) — фабрика из доменного `Room`. Маппинг статуса:

```python
if room.is_paused:    status = "pausing"
elif room.is_loaded:  status = "playing"
else:                 status = "waiting"
```

То есть `is_paused` имеет приоритет над `is_loaded` при формировании строки статуса.

### 4.4. Поток REST-запроса (шаг за шагом, на примере `POST /api/rooms`)

1. Uvicorn принимает HTTP, FastAPI матчит маршрут на `create_room` (`room/router.py:11`).
2. Тело валидируется в `RoomCreate`; невалидное → `422` автоматически.
3. Резолвится зависимость `get_room_service` → возвращается **один и тот же** модуль-синглтон `_room_service` (`room/dependencies.py:3`).
4. `RoomCreate` расширяется до `RoomInternal(**data.model_dump())` — добавляются `room_id` и `created_at`.
5. `room_service.create_room(internal)` создаёт `Room(**schema.model_dump())` и кладёт в `_storage[room.room_id]` (`room/service.py:13-16`).
6. `RoomResponse.from_room(room)` сериализует домен в ответ; FastAPI отдаёт `201` + JSON.

Для `rezka`-эндпоинтов шаг 5 заменяется на `await service.<method>(...)` (см. §5) — там есть await на сетевой запрос к rezka.ag.

---

## 5. Модуль Rezka (`app/modules/rezka`)

Отдельный data-access модуль для скрейпинга rezka.ag. Полностью **async** (это инвариант, проверяемый линтером — см. §11).

| Файл | Содержимое |
|---|---|
| `router.py` | REST-эндпоинты `/api/rezka/*` (`tags=["Rezka"]`) |
| `service.py` | `RezkaService` (поиск/инфо) и `RezkaStream` (источники видео) |
| `_base.py` | `RezkaBase` — общий async HTTP-клиент поверх `httpx.AsyncClient` |
| `_decoder.py` | `StreamDecoder` — декодирование обфусцированных URL потоков |
| `schemas.py` | Pydantic-модели ответов |
| `dependencies.py` | синглтоны `_rezka_service`, `_rezka_stream` |

### 5.1. Эндпоинты (`rezka/router.py`)

| Метод | Путь | Хендлер | Зависимость | Назначение |
|---|---|---|---|---|
| `GET` | `/api/rezka/quick_search` | `quick_search` `:19` | `RezkaService` | быстрый AJAX-поиск по названию |
| `GET` | `/api/rezka/search` | `search` `:27` | `RezkaService` | полный поиск (опц. `limit`) |
| `GET` | `/api/rezka/quick_info_movie` | `quick_info_movie` `:36` | `RezkaService` | краткая карточка по `movie_id` |
| `GET` | `/api/rezka/info_movie` | `info_movie` `:44` | `RezkaService` | полная инфо по `movie_url` (id, переводы, тип контента) |
| `GET` | `/api/rezka/movie_source` | `movie_source` `:52` | `RezkaStream` | ссылки на поток фильма (`movie_id`, `translator_id`) |
| `GET` | `/api/rezka/series_source` | `series_source` `:61` | `RezkaStream` | сезоны/эпизоды + ссылки (`series_id`, `translator_id`, опц. `season`, `episode`) |

### 5.2. HTTP-база (`rezka/_base.py`)

`RezkaBase` — базовый класс для `RezkaService` и `RezkaStream`.

- `URL = httpx.URL(settings.REZKA_URL)`, `PROXIES_LIST = settings.PROXIES_LIST` — атрибуты класса (`_base.py:17-18`).
- `_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)` (`_base.py:13`) — подобран под медленный публичный rezka.ag.
- `_request` (`_base.py:31-48`) на каждый вызов создаёт **новый** `httpx.AsyncClient(proxy=..., timeout=..., follow_redirects=True)`, делает запрос, `raise_for_status()`. Ошибки `httpx.HTTPError` логируются warning'ом и **пробрасываются** (превращаются в `500`).
- `_get_random_proxy` (`_base.py:20-23`) — случайный прокси из `PROXIES_LIST` или `None`.
- `get` / `post` имеют `@overload` по `is_json`: при `is_json=True` возвращается `dict` (через `response.json()`), иначе `BeautifulSoup`.
- `get_text` — статический безопасный экстрактор текста из тега (или `None`).

### 5.3. Декодер потоков (`rezka/_decoder.py`)

`StreamDecoder.decode` (`:26-49`) разбирает обфусцированную base64-строку Rezka: срезает первые 2 символа, дважды вычищает разделитель `//_//` и «мусорные» подстроки из `_TRASH_LIST`, декодирует base64, парсит качества по `_QUALITY_PATTERN` и берёт `.mp4`-ссылки. Качество `"1080p Ultra"` намеренно пропускается. Пустой вход → `ValueError`.

---

## 6. WS-слой (`app/ws/router.py`)

Единственный эндпоинт: `@router.websocket("/{room_id}")` → `websocket_endpoint` (`ws/router.py:16-55`). Зависимость — тот же `get_room_service`.

### 6.1. Поток WS-сессии (шаг за шагом)

1. **Accept.** `await websocket.accept()` (`:22`) — соединение принимается **до** любых проверок (иначе нельзя отправить `close` с кодом).
2. **Поиск комнаты.** `room = room_service.get_room(room_id)` (`:24`). Если `None` → `close(code=4000, reason="Room not found")` и выход (`:25-27`). Комнату создают только через REST (`POST /api/rooms`).
3. **Handshake.** Ждём первое сообщение `await websocket.receive_json()` и валидируем в `ConnectMessage` (`:30-31`). При **любом** исключении (`ValidationError` или иное) → `close(code=4001, reason="Authentication is required")` (`:32-34`). `ConnectMessage` (`ws/schemas.py`) требует `type: Literal["connect"]` и `name: str`.
4. **Регистрация.** Создаётся `user = User(connect.name, websocket)` (`:36`), затем `await room.add_user(user)` (под локом, §9). Создаётся `handler = UserHandler(user, room)`.
5. **Ответ.** Сервер шлёт `{"type": "connect", "id": user.user_id}` (`:39`) — клиент узнаёт свой `uuid`.
6. **Главный цикл.** `while True: data = await websocket.receive_json(); await handler.handle(data)` (`:41-44`).
7. **Завершение.**
   - `WebSocketDisconnect` (`:45`) — штатный разрыв, лог `info`.
   - Любое другое `Exception` (`:47`) — лог `error`, попытка `close(code=1011)`; если сокет уже закрыт клиентом — `close_err` логируется `debug` и игнорируется (`:51-53`).
   - **`finally: await room.remove_user(user)`** (`:54-55`) — гарантированное удаление из комнаты в любом случае. Удалять напрямую `room.user_storage.remove(user)` нельзя — только идемпотентный `remove_user` под локом.

### 6.2. Коды закрытия WebSocket

| Код | Когда | Смысл |
|---|---|---|
| `4000` | комната не найдена | прикладной: `Room not found` |
| `4001` | нет/невалидный `connect` первым сообщением | прикладной: `Authentication is required` |
| `1011` | необработанное исключение в цикле | стандартный Internal Error |

---

## 7. Обработчик сообщений (`app/modules/room/handler.py`)

`UserHandler` владеет парой `(user, room)` и транслирует входящие WS-сообщения в действия над `Room`.

### 7.1. Допустимые действия

```python
_VALID_ACTIONS = frozenset({"play", "pause", "status", "load", "set_video", "info"})
```

`handle` (`handler.py:20-45`): берёт `data.get("type")`; если действие **не** в `_VALID_ACTIONS` — молча выходит (`return`). Это намеренный фильтр от мусора, но он же породил исторический баг: действие в множестве **без** реализации «принимается без эффекта». Поэтому каждое значение в `_VALID_ACTIONS` обязано иметь обработчик — это проверяется линтером (§11).

### 7.2. Маршрутизация в `handle`

| `type` | Что делает | Метод |
|---|---|---|
| `info` | пишет в `user.info` все поля кроме `type` и выходит (`:27-29`) | inline |
| `set_video` | делегирует и выходит (`:31-33`) | `_handle_set_video` |
| `play` / `pause` / `status` / `load` | сначала обновляет `user.current_time` и `user.downloaded_time` из `data` (`:35-36`), затем диспетчеризует | `_handle_*` |

Обновление `current_time` / `downloaded_time` (`:35-36`) делается через `float(data.get(...) or 0)` — отсутствующее или `0`-ложное поле превращается в `0.0`. Для `info` и `set_video` это обновление **не** выполняется (они выходят раньше).

### 7.3. Конкретные обработчики

**`_handle_status`** (`:47-59`) — основной «пинг готовности».
- Если комната ещё `not is_loaded` → `await room.check_is_loaded(self.user)` (§8.3). При готовности: если `is_paused` — `remove_block_pause()`, иначе `play()`.
- Затем формирует broadcast: копия `data` без `current_time`, с `type="info"` и `name=user.name`, и рассылает всем, кроме отправителя.

**`_handle_play`** (`:61-67`)
- `seek(current_time, self.user)` — разослать позицию всем, кроме себя.
- `room.load(current_time)` — зафиксировать позицию комнаты и сбросить `is_loaded`.
- `is_paused = False`.
- если `check_is_loaded` → `room.play()`.

**`_handle_pause`** (`:69-76`)
- `seek(current_time, self.user)` — сообщить позицию остальным.
- `room.pause(self.user)` — поставить на паузу всех, **кроме** инициатора (он уже на паузе локально). Без этого второго вызова остальные продолжали бы играть.
- `room.load(current_time)`, `is_paused = True`.

**`_handle_load`** (`:78-86`) — клиент просит пересинхронизироваться.
- `room.load(current_time)`; если `check_is_loaded`: `is_paused` → `remove_block_pause()`, иначе `play()`.

**`_handle_set_video`** (`:88-95`) — сменить видео для всей комнаты.
- URL берётся из `data["video_url"]` или `data["url"]`; если не строка/пустой — warning и выход.
- `room.set_video_broadcast(video_url, current_time)` — обновляет состояние и рассылает всем.

**`_broadcast`** (`:16-18`) — `asyncio.gather` отправки `data` всем `get_users_exc(self.user)` (всем, кроме себя).

---

## 8. Доменная модель (`app/modules/room/models.py`)

### 8.1. `User` (`models.py:13-21`)

| Атрибут | Тип | Инициализация |
|---|---|---|
| `user_id` | `str` | `str(uuid4())` |
| `name` | `str` | из `connect.name` |
| `websocket` | `WebSocket` | сокет соединения |
| `current_time` | `float` | `0.0` |
| `downloaded_time` | `float` | `0.0` |
| `info` | `dict[str, Any]` | `{}` |

У `User` нет кастомного `__eq__` — сравнение в `get_users_exc` идёт по идентичности объекта.

### 8.2. `Room` — состояние (`models.py:24-43`)

| Атрибут | Тип | Смысл |
|---|---|---|
| `room_id`, `name`, `video_url` | `str` | идентификация и текущее видео |
| `current_time` | `float` | целевая позиция комнаты, к которой подтягиваются все |
| `is_paused` | `bool` | комната на паузе |
| `is_loaded` | `bool` | все участники догрузились и синхронизированы |
| `user_storage` | `list[User]` | участники |
| `created_at` | `datetime` | момент создания |
| `_lock` | `asyncio.Lock` | сериализация мутаций состава/готовности (§9) |

### 8.3. `Room` — методы

| Метод | Под локом? | Что делает |
|---|---|---|
| `add_user` `:45-47` | **да** | `user_storage.append(user)` |
| `remove_user` `:49-52` | **да** | удаляет, если есть (идемпотентно) |
| `set_video` `:54-58` | нет | меняет `video_url`/`current_time`, сбрасывает `is_loaded`/`is_paused` |
| `get_users_exc` `:60-61` | нет | список всех, кроме `exception_user` |
| `load` `:63-65` | нет | задаёт `current_time`, сбрасывает `is_loaded` |
| `check_is_loaded` `:67-83` | **да** | проверка готовности + коррекция отстающих (см. ниже) |
| `play` `:85-87` | нет | broadcast `{"type":"play"}` всем |
| `pause` `:89-92` | нет | broadcast `{"type":"pause"}` всем, кроме `exception_user` |
| `seek` `:94-105` | нет | broadcast `{"type":"seek","current_time":...}`; если задан `user` — только ему |
| `set_video_broadcast` `:107-116` | нет | `set_video` + broadcast `{"type":"set_video",...}` всем |
| `remove_block_pause` `:118-119` | нет | broadcast `{"type":"remove_block_pause"}` всем |

**`check_is_loaded`** — ядро логики синхронизации (`models.py:67-83`):

1. Находит «отстающих» — `u.current_time != self.current_time`.
2. Если такие есть — рассылает им `{"type":"seek","current_time": self.current_time}` (через `asyncio.gather`). Без этой коррекции один отстающий навсегда блокировал бы старт.
3. `all_ready = len(user_storage) > 0 AND все имеют current_time == room.current_time И downloaded_time >= settings.REQUIRED_DOWNLOAD_TIME`.
4. Если готовы — `is_loaded = True`. Возвращает `all_ready`.

> Это **единственное** место, где `send_json` выполняется **под локом** — и сознательно: рассылка отстающим ограничена и быстра. Все «тяжёлые» broadcast'ы (`play`/`pause`/`seek`/`set_video_broadcast`) вынесены за пределы лока — см. §9.

`seek` (`:94-105`) имеет тройную сигнатуру:
```python
async def seek(self, current_time, exception_user=None, user=None) -> None
```
- если передан `user` — `seek` адресный, только этому пользователю, и сразу `return`;
- иначе — рассылка всем, кроме `exception_user`.

---

## 9. Сериализация под `asyncio.Lock` и правило отсутствия дедлока

`Room._lock` — **нереентрантный** `asyncio.Lock` (`models.py:43`). Он сериализует операции, которые читают/меняют `user_storage` и флаг готовности при конкурентных WS-соединениях:

- `add_user` (`:46`)
- `remove_user` (`:50`)
- `check_is_loaded` (`:68`)

### Правило: не вызывайте `room.play()` / `room.seek()` / `room.pause()` изнутри `async with self._lock`

`play`/`pause`/`seek`/`set_video_broadcast`/`remove_block_pause` сами лок **не берут** — они только рассылают через `send_json`. Запрет вызывать их внутри удерживаемого лока обусловлен тем, что:

1. Внутри лока уже идёт `await` на сетевой `send_json` (точка переключения корутин).
2. Пока лок удерживается, любой параллельный `_handle_*`, которому нужен `add_user`/`remove_user`/`check_is_loaded`, **блокируется** в ожидании лока.
3. Сетевая отправка может стопориться (медленный/мёртвый клиент), удлиняя удержание лока и вызывая каскадную блокировку всей комнаты — фактически дедлок по доступности.

**Корректный паттерн** (как сделано в `_handle_status` / `_handle_load`): сначала `await room.check_is_loaded(...)` — лок берётся и **освобождается внутри** метода; и только **после** возврата (лок уже отпущен) вызывается `room.play()` / `room.remove_block_pause()`. Рассылка всегда происходит **вне** лока.

Если потребуется разослать что-то на основе данных, прочитанных под локом, — выйдите из лока (или соберите данные внутри, а рассылайте снаружи), а не вызывайте broadcast внутри `async with self._lock`.

---

## 10. Внедрение зависимостей и in-memory `RoomService`

### 10.1. Паттерн DI

Модуль предоставляет провайдер-функцию, FastAPI резолвит её через `Depends`:

```python
# app/modules/room/dependencies.py
_room_service = RoomService()          # модуль-глобальный синглтон
def get_room_service() -> RoomService:
    return _room_service
```

Оба входа в систему — REST (`room/router.py`) и WS (`ws/router.py`) — объявляют `room_service: RoomService = Depends(get_room_service)` и получают **один и тот же** экземпляр. Аналогично `rezka/dependencies.py` отдаёт синглтоны `_rezka_service` и `_rezka_stream`.

> В `pyproject.toml` для `*/router.py` отключено правило `B008` (`flake8-bugbear`: вызов функции в дефолте аргумента) — `Depends(...)` в сигнатуре это и есть, и для FastAPI это норма.

### 10.2. `RoomService` (`app/modules/room/service.py`)

In-memory хранилище комнат. **Без персистентности**: `_storage: dict[str, Room]` живёт в памяти процесса.

| Метод | Поведение |
|---|---|
| `rooms` (property) `:9-11` | весь `_storage` (используется в `list_rooms`) |
| `create_room(schema)` `:13-16` | `Room(**schema.model_dump())`, кладёт в `_storage` по `room_id` |
| `get_room(room_id)` `:18-19` | `_storage.get(room_id)` или `None` |
| `update_room(room_id, update)` `:21-27` | `setattr` по `model_dump(exclude_unset=True)`; `None` если нет |
| `delete_room(room_id)` `:29-34` | `False`, если комнаты нет **или** `room.user_storage` непустой; иначе удаляет и `True` |

Следствия дизайна (важно не «чинить то, что не сломано»):

- **Перезапуск процесса теряет все комнаты.** Это согласованное ограничение; переход на Redis/Postgres делать не нужно без явного запроса.
- **Нет автоудаления пустых комнат** — только ручной `DELETE`, и то лишь при отсутствии активных пользователей.
- **Один процесс — одно состояние.** Несколько воркеров uvicorn НЕ будут делить `_storage` (каждый получит свой синглтон). Сервис рассчитан на запуск в один процесс (`docker-compose.yml` запускает один `uvicorn` без `--workers`).
- В тестах глобальный синглтон обнуляется автофикстурой `_reset_room_storage` (`tests/conftest.py`), которая чистит `_room_service._storage` до и после каждого теста.

---

## 11. Принудительные архитектурные правила (`scripts/arch_lint_api.py`)

Гард архитектуры лежит в корне репозитория-обёртки: `D:\Projects\Sync-Mate\scripts\arch_lint_api.py` (рядом с `arch_lint_ext.py` для расширения). Чистый stdlib, regex/AST, запускается `python scripts/arch_lint_api.py [--root <repo>]`; exit `0` — чисто, `1` — нарушения. По умолчанию `--root` = cwd.

Три проверки:

1. **Направление слоёв** (`check_layers`, `:62-76`).
   - Любой файл под `app/modules/**` не должен импортировать `app.api`, `app.ws`, `app.main`.
   - Изоляция модулей-сиблингов: `app/modules/rezka/*` не импортирует `app.modules.room` и наоборот.
2. **Паритет WS-действий и обработчиков** (`check_action_parity`, `:79-97`).
   - Парсит `_VALID_ACTIONS = frozenset({...})` из `app/modules/room/handler.py`.
   - Для каждого действия требует наличие либо метода `def _handle_<action>`, либо инлайн-ветки `action == "<action>"`. Иначе — нарушение «silently accepted with no effect». Если само множество не найдено — тоже нарушение.
3. **Только async-HTTP** (`check_no_sync_http`, `:100-107`).
   - Запрещает `import requests` / `from requests` и синхронный `httpx.Client(` где-либо под `app/`. Использовать только `httpx.AsyncClient`.

Эти правила формализуют инварианты, описанные в `Sync-Mate-API-WS/CLAUDE.md`: однонаправленные зависимости, обязательная реализация каждого действия, и async-only доступ к Rezka.

### Сопутствующие конвенции качества (`pyproject.toml`, CI)

- Форматирование: `black` + `isort` (профиль black, line-length **120**).
- Линт: `flake8` + `flake8-bugbear`; per-file: `__init__.py:F401`, `*/router.py:B008`.
- Типы: `mypy app` (строгий, `python_version = "3.11"`).
- Безопасность: `bandit -r app` (skips `B101`, `B104`), `safety check`.
- Тесты: `pytest` с `--strict-markers --strict-config`, `filterwarnings=["error", ...]`; маркер `asyncio` ставится **явно** на каждый async-тест (нет `asyncio_mode=auto`).

---

## 12. Сборка, запуск и деплой (реальность кода)

> Этот раздел корректирует устаревшие места корневого `DOCUMENTATION.md`.

### 12.1. Локальный запуск

```bash
poetry install
poetry run uvicorn app.main:app --reload        # http://127.0.0.1:8000
poetry run pytest                                # тесты
```

`Makefile`: `make dev` (uvicorn `0.0.0.0:$PORT`, reload), `make up`/`make down`/`make logs` (docker compose, проект `sync-mate`), `make tunnel`/`make tunnel-quick`/`make run` (Cloudflare-туннель). Цели туннеля используют `CLOUDFLARE_TUNNEL_TOKEN` из `.env`, но это **только локальный инструмент** — в продакшен-композ туннель не входит.

### 12.2. Docker / `docker-compose.yml`

Текущий `docker-compose.yml` содержит **один сервис** — `sync-mate-api-ws` (образ `ghcr.io/zebaro24/sync-mate-api-ws:latest`, порт `${SERVER_PORT:-8000}:8000`, `restart: unless-stopped`). Сервис `cloudflared` был **удалён** из компоуза в коммите `f0c7443` («Remove cloudflared from docker-compose»). Если в старой документации фигурирует двухсервисный compose с туннелем — это устаревшая информация.

`Dockerfile`: база `python:3.13-slim`, Poetry ставит зависимости без dev-группы (`--without dev`), запуск `uvicorn app.main:app --host 0.0.0.0 --port 8000` (один процесс, без `--workers`).

### 12.3. CI/CD

- **CI (`.github/workflows/ci.yml`)** — четыре job'а (`lint-format`, `type-check`, `security`, `test`), все на **Python 3.13 ONLY**. Никаких 3.11/3.12 в матрице нет (см. коммит `20990d5` «Test only on Python 3.13»). Тесты гоняются с покрытием и аплоадом в Codecov.
- **CD (`.github/workflows/cd.yml`)** — по тегу `v*`: сборка и пуш образа в GHCR, затем деплой по SSH (копирование `docker-compose.yml` на сервер и `docker compose up -d --pull always`).

> `pyproject.toml` объявляет `python = "^3.11"` (нижняя граница совместимости), но и Docker-образ, и весь CI используют 3.13. Для воспроизводимости ориентируйтесь на 3.13.

---

## См. также

- [`../CLAUDE.md`](../CLAUDE.md) — гид по бэкенд-части (стек, запуск, инварианты, что НЕ делать).
- [`../../CLAUDE.md`](../../CLAUDE.md) — общий гид по репозиторию Sync-Mate (оба подпроекта).
- [`../../DOCUMENTATION.md`](../../DOCUMENTATION.md) — полная техническая документация и контракт WS-протокола (раздел про деплой устарел — см. §12 выше).
- [`../../Sync-Mate-Extension/CLAUDE.md`](../../Sync-Mate-Extension/CLAUDE.md) — гид по расширению (другая сторона WS-протокола).
- `../../scripts/arch_lint_api.py` — гард архитектуры бэкенда (§11); `../../scripts/arch_lint_ext.py` — аналог для расширения.
- `../README.md` — краткое README подпроекта.
