# REST API — Sync-Mate-API-WS

Полный справочник по HTTP REST-эндпоинтам сервиса Sync-Mate-API-WS: управление комнатами (CRUD + редирект) и доступ к данным Rezka (поиск, информация, источники видео).

---

## Общие сведения

### Базовый адрес и префикс

Все REST-маршруты монтируются под единым префиксом **`/api`** — он добавляется в `app/main.py:61`:

```python
app.include_router(api_router, prefix="/api")   # REST
app.include_router(ws_router,  prefix="/ws")    # WebSocket (см. ws-protocol.md)
```

Внутри `app/api/router.py` подмаршруты добавляют ещё по сегменту:

```python
router.include_router(room_router,  prefix="/rooms")    # app/api/router.py:9
router.include_router(rezka_router, prefix="/rezka")     # app/api/router.py:10
```

Итоговые базы:

| Окружение | Базовый URL | Откуда |
|---|---|---|
| Локальная разработка | `http://127.0.0.1:8000` | `uvicorn app.main:app --reload` (README) |
| Docker | `http://<host>:${SERVER_PORT:-8000}` | `docker-compose.yml:7-8` |
| Production | `https://sync-mate-api-ws.zebaro.dev` | `.github/workflows/cd.yml` (environment `prod`) |

> Везде ниже путь указан **полностью, вместе с префиксом `/api`**. Например, создание комнаты — это `POST /api/rooms`, а не `POST /rooms`.

### Аутентификация

Аутентификации нет (PATCH/DELETE пока не привязаны к создателю — см. бэклог BE-6). CORS открыт по
origin, но **без credentials** (`app/main.py`):

```python
allow_origins=["*"], allow_credentials=False,
allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"], allow_headers=["*"]
```

Origin не сужаем (расширение зовёт API с разных origin: страница Rezka, `chrome-extension://…`),
но `allow_credentials=False` убирает опасную связку `*` + куки — чужой сайт не сможет действовать
в контексте пользователя. Куки/credentials API и так не использует.

### Форматы

- Тело запроса и ответа — `application/json` (кроме `GET /api/rooms/{room_id}/redirect`, который отдаёт HTTP-редирект).
- Кодировка — UTF-8.
- Ошибки валидации FastAPI/Pydantic возвращаются с кодом **422** в стандартном формате `{"detail": [...]}`.
- Ошибки уровня приложения возвращаются как `{"detail": "<текст>"}` (через `HTTPException`).

### Интерактивная документация

FastAPI автоматически публикует (заголовок и версия берутся из `Settings`, см. `app/main.py:46-51`):

| URL | Назначение |
|---|---|
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |
| `/openapi.json` | OpenAPI-схема |

### Карта эндпоинтов

| Метод | Путь | Тег | Назначение |
|---|---|---|---|
| `GET` | `/api/info` | General | Метаданные сервиса |
| `POST` | `/api/rooms` | Rooms | Создать комнату |
| `GET` | `/api/rooms` | Rooms | Список всех комнат |
| `GET` | `/api/rooms/{room_id}` | Rooms | Получить комнату |
| `PATCH` | `/api/rooms/{room_id}` | Rooms | Частично обновить комнату |
| `DELETE` | `/api/rooms/{room_id}` | Rooms | Удалить комнату |
| `GET` | `/api/rooms/{room_id}/redirect` | Rooms | Редирект на `video_url` комнаты |
| `GET` | `/api/rezka/quick_search` | Search | Быстрый поиск (ajax) |
| `GET` | `/api/rezka/search` | Search | Полный поиск с лимитом |
| `GET` | `/api/rezka/quick_info_movie` | Info | Краткая карточка по `movie_id` |
| `GET` | `/api/rezka/info_movie` | Info | Полная карточка по URL |
| `GET` | `/api/rezka/movie_source` | Stream | Источники видео для фильма |
| `GET` | `/api/rezka/series_source` | Stream | Источники видео для сериала |

---

## Раздел: General

### `GET /api/info`

**Источник:** `app/api/router.py:13-20`

Возвращает статическую информацию о сервисе из `Settings` (`app/config.py:4-14`). Никаких параметров не принимает.

**Ответ `200 OK`**

| Поле | Тип | Источник | Пример |
|---|---|---|---|
| `name` | `str` | `settings.app_name` | `"Sync-Mate-API-WS"` |
| `description` | `str` | `settings.description` | `"SyncMate API WS is a REST and WebSocket service ..."` |
| `author` | `str` | `settings.author` | `"Zebaro (zebaro.dev)"` |
| `version` | `str` | `settings.version` | `"0.1.1"` |

**Пример запроса**

```bash
curl http://127.0.0.1:8000/api/info
```

**Пример ответа**

```json
{
  "name": "Sync-Mate-API-WS",
  "description": "SyncMate API WS is a REST and WebSocket service providing synchronized video playback control, metadata streams, and video sources retrieval from YouTube and Rezka.ag.",
  "author": "Zebaro (zebaro.dev)",
  "version": "0.1.1"
}
```

---

## Раздел: Rooms

### Доменная модель и схемы

Комната хранится в памяти как объект `Room` (`app/modules/room/models.py:24-43`), а наружу всегда отдаётся через `RoomResponse` (`app/modules/room/schemas.py:33-68`). Состояние комнат хранится **в едином in-memory словаре** внутри singleton-сервиса `RoomService` (`app/modules/room/dependencies.py:3-7`, `app/modules/room/service.py:5-7`) — при перезапуске процесса все комнаты теряются.

#### Объект комнаты — `RoomResponse`

| Поле | Тип | Описание |
|---|---|---|
| `room_id` | `str` (UUID4) | Идентификатор. Генерируется автоматически при создании (`RoomInternal`, `schemas.py:21`). |
| `name` | `str` | Имя комнаты. |
| `video_url` | `str` | Текущий URL видео (на него ведёт `/redirect`). |
| `current_time` | `float` | Текущая позиция воспроизведения в секундах (состояние комнаты, не пользователя). |
| `created_at` | `datetime` (ISO 8601, UTC) | Время создания. Генерируется автоматически (`schemas.py:22`). |
| `status` | `str` | Состояние комнаты (см. таблицу ниже). По умолчанию `"waiting"` (`schemas.py:34`). |
| `users` | `list[UserResponse]` | Список подключённых по WebSocket участников. Пусто, пока никто не подключился. |
| `link` | `str` (computed) | Готовый относительный путь редиректа: `"/api/rooms/{room_id}/redirect"` (`schemas.py:37-40`). |

> `link` — вычисляемое поле (`@computed_field`): оно присутствует в ответе, но его **нельзя** передавать в теле запроса.

#### Вложенный объект участника — `UserResponse`

Источник: `app/modules/room/schemas.py:25-30`. Заполняется из WebSocket-сессий (`User`, `models.py:13-21`).

| Поле | Тип | Описание |
|---|---|---|
| `user_id` | `str` (UUID4) | Идентификатор участника (выдаётся при WS-`connect`). |
| `name` | `str` | Имя, переданное при подключении. |
| `current_time` | `float` | Позиция воспроизведения у конкретного участника. |
| `downloaded_time` | `float` | Сколько секунд видео буферизовано у участника. Сверяется с `REQUIRED_DOWNLOAD_TIME` (= `15`, `config.py:17`) при определении готовности. |
| `info` | `dict` | Произвольные метаданные участника (приходят WS-сообщением `info`). |

#### Значения `status`

Статус **вычисляется на лету** в `RoomResponse.from_room` (`app/modules/room/schemas.py:42-50`) из булевых флагов `Room.is_paused` / `Room.is_loaded`. Порядок проверок важен — `is_paused` имеет приоритет:

```python
if room.is_paused:      status = "pausing"
elif room.is_loaded:    status = "playing"
else:                   status = "waiting"
```

| `status` | Условие | Что означает |
|---|---|---|
| `waiting` | `is_paused == False` и `is_loaded == False` | Идёт ожидание готовности участников (буферизация/синхронизация позиции). Состояние по умолчанию для свежесозданной комнаты. |
| `playing` | `is_paused == False` и `is_loaded == True` | Все участники синхронизированы и догрузились — комната воспроизводит. |
| `pausing` | `is_paused == True` | Комната на паузе (приоритетнее `playing`: даже при `is_loaded == True` вернётся `pausing`). |

> **Внимание (расхождение):** в REST-ответе нет строки `"paused"`. Состояние паузы кодируется именно как **`pausing`** (`schemas.py:45`). Если в старой документации встречается `paused` — это устаревшее название; реальный код отдаёт `pausing`.
>
> Флаги меняются на WebSocket-слое (`app/modules/room/handler.py`): `play` сбрасывает `is_paused`, `pause` ставит `is_paused = True`, а готовность (`is_loaded`) выставляет `Room.check_is_loaded` после того, как все участники догрузили ≥ `REQUIRED_DOWNLOAD_TIME` секунд и сошлись по `current_time`. Через REST статус не управляется (см. примечание к `PATCH`).

---

### `POST /api/rooms`

**Источник:** `app/modules/room/router.py:11-18`

Создаёт новую комнату. `room_id` и `created_at` назначаются сервером (поля `RoomInternal`), их передавать не нужно.

**Тело запроса — `RoomCreate`** (`app/modules/room/schemas.py:8-11`)

| Поле | Тип | Обязательное | По умолчанию | Описание |
|---|---|---|---|---|
| `name` | `str` | да | — | Имя комнаты. |
| `video_url` | `str` | да | — | Стартовый URL видео. |
| `current_time` | `float` | нет | `0.0` | Стартовая позиция в секундах. |

**Ответ `201 Created`** — объект `RoomResponse` (`status_code=201` задан явно в декораторе).

**Коды ответа**

| Код | Когда |
|---|---|
| `201` | Комната создана. |
| `422` | Отсутствует `name`/`video_url` или неверные типы. |

**Пример запроса**

```bash
curl -X POST http://127.0.0.1:8000/api/rooms \
  -H "Content-Type: application/json" \
  -d '{"name": "Вечерний киносеанс", "video_url": "https://rezka.ag/films/.../123-...html", "current_time": 0}'
```

**Пример ответа**

```json
{
  "name": "Вечерний киносеанс",
  "video_url": "https://rezka.ag/films/.../123-...html",
  "current_time": 0.0,
  "room_id": "3f2b6c1e-9a4d-4f0e-8b2a-1c5d7e9f0a11",
  "created_at": "2026-06-27T18:30:00.123456+00:00",
  "status": "waiting",
  "users": [],
  "link": "/api/rooms/3f2b6c1e-9a4d-4f0e-8b2a-1c5d7e9f0a11/redirect"
}
```

---

### `GET /api/rooms`

**Источник:** `app/modules/room/router.py:21-25`

Возвращает массив всех комнат, находящихся в памяти (`room_service.rooms.values()`). Параметров нет. Пагинации/фильтрации нет.

> ⚠️ **Только для отладки.** Полный список комнат — это утечка/энумерация (id, video_url, ники),
> поэтому отдаётся **лишь при `settings.debug=True`**. В проде (`debug=False`) эндпоинт возвращает
> `404 Not Found`. Расширением не используется.

**Ответ `200 OK`** (только в debug) — `list[RoomResponse]` (может быть пустым `[]`).
**Ответ `404 Not Found`** — в проде (`debug=False`).

**Пример запроса**

```bash
curl http://127.0.0.1:8000/api/rooms
```

**Пример ответа**

```json
[
  {
    "name": "Вечерний киносеанс",
    "video_url": "https://rezka.ag/films/.../123-...html",
    "current_time": 42.5,
    "room_id": "3f2b6c1e-9a4d-4f0e-8b2a-1c5d7e9f0a11",
    "created_at": "2026-06-27T18:30:00.123456+00:00",
    "status": "playing",
    "users": [
      {
        "user_id": "a1b2c3d4-0000-1111-2222-333344445555",
        "name": "Денис",
        "current_time": 42.5,
        "downloaded_time": 70.0,
        "info": {"quality": "720p"}
      }
    ],
    "link": "/api/rooms/3f2b6c1e-9a4d-4f0e-8b2a-1c5d7e9f0a11/redirect"
  }
]
```

---

### `GET /api/rooms/{room_id}`

**Источник:** `app/modules/room/router.py:28-36`

Возвращает одну комнату по идентификатору.

**Path-параметры**

| Параметр | Тип | Описание |
|---|---|---|
| `room_id` | `str` | UUID комнаты. |

**Коды ответа**

| Код | Когда |
|---|---|
| `200` | Комната найдена → `RoomResponse`. |
| `404` | `{"detail": "Room not found"}` (`router.py:35`). |

**Пример запроса**

```bash
curl http://127.0.0.1:8000/api/rooms/3f2b6c1e-9a4d-4f0e-8b2a-1c5d7e9f0a11
```

**Пример ответа `404`**

```json
{ "detail": "Room not found" }
```

---

### `PATCH /api/rooms/{room_id}`

**Источник:** `app/modules/room/router.py:39-48`, логика — `RoomService.update_room` (`service.py:21-27`)

Частичное обновление. Применяются только **явно переданные** поля (`model_dump(exclude_unset=True)`), остальные не трогаются.

**Path-параметры**

| Параметр | Тип | Описание |
|---|---|---|
| `room_id` | `str` | UUID комнаты. |

**Тело запроса — `RoomUpdate`** (`app/modules/room/schemas.py:14-17`) — все поля необязательны:

| Поле | Тип | По умолчанию | Описание |
|---|---|---|---|
| `name` | `str \| null` | `None` | Новое имя. |
| `video_url` | `str \| null` | `None` | Новый URL видео. |
| `current_time` | `float \| null` | `None` | Новая позиция. |

**Коды ответа**

| Код | Когда |
|---|---|
| `200` | Обновлено → `RoomResponse`. |
| `404` | `{"detail": "Room not found"}` (`router.py:47`). |
| `422` | Неверные типы переданных полей. |

> **Подводный камень.** `update_room` делает `setattr(room, field, value)` напрямую по полям `Room`. Менять можно только `name` / `video_url` / `current_time` (это всё, что есть в `RoomUpdate`). Статус (`status`) через REST задать нельзя — это computed-значение, выводимое из `is_paused`/`is_loaded`, которыми управляет WebSocket-слой. Установка `video_url` через `PATCH` напрямую присваивает атрибут и **не** рассылает участникам `set_video` (это делает только WS-обработчик `set_video`, `handler.py:88-95`).

**Пример запроса**

```bash
curl -X PATCH http://127.0.0.1:8000/api/rooms/3f2b6c1e-9a4d-4f0e-8b2a-1c5d7e9f0a11 \
  -H "Content-Type: application/json" \
  -d '{"name": "Новое имя", "current_time": 120.0}'
```

**Пример ответа**

```json
{
  "name": "Новое имя",
  "video_url": "https://rezka.ag/films/.../123-...html",
  "current_time": 120.0,
  "room_id": "3f2b6c1e-9a4d-4f0e-8b2a-1c5d7e9f0a11",
  "created_at": "2026-06-27T18:30:00.123456+00:00",
  "status": "waiting",
  "users": [],
  "link": "/api/rooms/3f2b6c1e-9a4d-4f0e-8b2a-1c5d7e9f0a11/redirect"
}
```

---

### `DELETE /api/rooms/{room_id}`

**Источник:** `app/modules/room/router.py:51-61`, логика — `RoomService.delete_room` (`service.py:29-34`)

Удаляет комнату. **Защита:** комнату с активными участниками удалить нельзя — `delete_room` возвращает `False`, если `room.user_storage` непустой (`service.py:31`), и эндпоинт отвечает `409`.

**Path-параметры**

| Параметр | Тип | Описание |
|---|---|---|
| `room_id` | `str` | UUID комнаты. |

**Пошаговый ход**

1. `get_room(room_id)` → если `None`, сразу `404 Room not found` (`router.py:57-58`).
2. `delete_room(room_id)` → если `False` (комната есть, но в ней есть участники), `409 Room has active users and cannot be deleted` (`router.py:60`).
3. Иначе комната удаляется из словаря, ответ `200`.

**Коды ответа**

| Код | Тело | Когда |
|---|---|---|
| `200` | `{"message": "Room deleted successfully"}` | Удалено. |
| `404` | `{"detail": "Room not found"}` | Нет такой комнаты. |
| `409` | `{"detail": "Room has active users and cannot be deleted"}` | В комнате есть подключённые по WS участники. |

**Пример запроса**

```bash
curl -X DELETE http://127.0.0.1:8000/api/rooms/3f2b6c1e-9a4d-4f0e-8b2a-1c5d7e9f0a11
```

**Пример ответа `200`**

```json
{ "message": "Room deleted successfully" }
```

---

### `GET /api/rooms/{room_id}/redirect`

**Источник:** `app/modules/room/router.py:64-72`

Отдаёт HTTP-редирект на текущий `video_url` комнаты. Это и есть «короткая ссылка», возвращаемая в поле `link`. Удобно для расшаривания: пользователь переходит по ссылке и попадает на актуальное видео комнаты.

**Path-параметры**

| Параметр | Тип | Описание |
|---|---|---|
| `room_id` | `str` | UUID комнаты. |

**Коды ответа**

| Код | Когда |
|---|---|
| `307` | `Temporary Redirect` с заголовком `Location: <room.video_url>` (`RedirectResponse(..., status_code=307)`). |
| `404` | `{"detail": "Room not found"}` (`router.py:71`). |

> Код `307` сохраняет метод и тело запроса при переходе. Тела ответа нет — только заголовок `Location`.

**Пример запроса**

```bash
# -I покажет заголовки с Location; -L заставит curl пройти по редиректу
curl -I http://127.0.0.1:8000/api/rooms/3f2b6c1e-9a4d-4f0e-8b2a-1c5d7e9f0a11/redirect
```

**Пример ответа (заголовки)**

```http
HTTP/1.1 307 Temporary Redirect
location: https://rezka.ag/films/.../123-...html
```

---

## Раздел: Rezka

Эндпоинты тонко оборачивают парсер `rezka.ag`. Сервисы (`RezkaService`, `RezkaStream`) — singleton-зависимости (`app/modules/rezka/dependencies.py`). Все обращения к Rezka выполняются **асинхронно** через `httpx.AsyncClient` с таймаутами `connect=5s / read=15s / write=10s` и опциональным случайным прокси из `PROXIES_LIST` (`app/modules/rezka/_base.py:13,20-23,31-48`).

### Обработка ошибок Rezka

В `_base.py:44-47` вызывается `response.raise_for_status()`; любая `httpx.HTTPError` (таймаут, 4xx/5xx от Rezka, сетевой сбой) логируется и **пробрасывается дальше**. Так как специального обработчика исключений нет, FastAPI превращает её в **`500 Internal Server Error`**. Аналогично `ValueError` при невозможности декодировать поток (`_decoder.py:28-35`) или извлечь `movie_id` (`service.py:104-105`) даёт `500`. Невалидные/отсутствующие query-параметры дают **`422`** (валидация FastAPI).

| Код | Когда |
|---|---|
| `200` | Успех — соответствующая схема ответа. |
| `422` | Отсутствует обязательный query-параметр или неверный тип (например, `movie_id` не число). |
| `500` | Ошибка обращения к Rezka, ошибка парсинга HTML или декодирования потока. |

> Пустой результат поиска — это не ошибка: возвращается `200` с пустым массивом `[]`.

---

### `GET /api/rezka/quick_search`

**Источник:** `app/modules/rezka/router.py:19-24` → `RezkaService.quick_search` (`service.py:25-47`)

Быстрый поиск через ajax-эндпоинт Rezka (`/engine/ajax/search.php`). Лёгкий, без обложек.

**Query-параметры**

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `movie_title` | `str` | да | Поисковый запрос. |

**Ответ `200 OK`** — `list[MovieQuickSearchResponse]` (`schemas.py:6-11`):

| Поле | Тип | Описание |
|---|---|---|
| `id` | `int` | ID тайтла на Rezka. |
| `title` | `str` | Название. |
| `alter_title` | `str` | Альтернативное (оригинальное) название. |
| `rating` | `str \| null` | Рейтинг/метка (например `"HD"`), если есть. |
| `url` | `str` | Полный URL карточки на Rezka. |

**Пример запроса**

```bash
curl "http://127.0.0.1:8000/api/rezka/quick_search?movie_title=Интерстеллар"
```

**Пример ответа**

```json
[
  {
    "id": 12345,
    "title": "Интерстеллар",
    "alter_title": "Interstellar (2014)",
    "rating": "HD",
    "url": "https://rezka.ag/films/fantasy/12345-interstellar.html"
  }
]
```

---

### `GET /api/rezka/search`

**Источник:** `app/modules/rezka/router.py:27-33` → `RezkaService.search` (`service.py:68-88`)

Полнотекстовый поиск через страницу `/search/`. Возвращает более богатые карточки (категория, подпись, обложка), поддерживает ограничение количества.

**Query-параметры**

| Параметр | Тип | Обязательный | По умолчанию | Описание |
|---|---|---|---|---|
| `movie_title` | `str` | да | — | Поисковый запрос. |
| `limit` | `int` | нет | `0` | Максимум результатов. `0` означает **без ограничения** (передаётся как `limit` в `soup.select(...)`, `service.py:75`). |

**Ответ `200 OK`** — `list[MovieSearchResponse]` (`schemas.py:23-29`):

| Поле | Тип | Описание |
|---|---|---|
| `id` | `int` | ID тайтла. |
| `title` | `str` | Название. |
| `category` | `str` | Категория (например `"Фильм"`, `"Сериал"`). |
| `caption` | `str` | Подпись/описание из карточки (годы, страны и т.п.). |
| `image` | `str` | URL обложки. |
| `url` | `str` | URL карточки (берётся из атрибута `data-url`). |

**Пример запроса**

```bash
curl "http://127.0.0.1:8000/api/rezka/search?movie_title=Интерстеллар&limit=5"
```

**Пример ответа**

```json
[
  {
    "id": 12345,
    "title": "Интерстеллар",
    "category": "Фильм",
    "caption": "2014, США, Великобритания / фантастика, драма",
    "image": "https://static.hdrezka.ac/i/2014/.../poster.jpg",
    "url": "https://rezka.ag/films/fantasy/12345-interstellar.html"
  }
]
```

---

### `GET /api/rezka/quick_info_movie`

**Источник:** `app/modules/rezka/router.py:36-41` → `RezkaService.quick_info_movie` (`service.py:49-66`)

Краткая карточка (через ajax `/engine/ajax/quick_content.php`) по числовому `movie_id`.

**Query-параметры**

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `movie_id` | `int` | да | ID тайтла (поле `id` из поиска). |

**Ответ `200 OK`** — `QuickInfoMovieResponse` (`schemas.py:14-20`):

| Поле | Тип | Описание |
|---|---|---|
| `id` | `int` | ID (эхо входного `movie_id`). |
| `title` | `str` | Название. |
| `category` | `str` | Категория. |
| `description` | `str` | Краткое описание. |
| `genres` | `list[str]` | Жанры (может быть пустым). |
| `rating` | `str \| null` | Рейтинг, если есть. |

**Пример запроса**

```bash
curl "http://127.0.0.1:8000/api/rezka/quick_info_movie?movie_id=12345"
```

**Пример ответа**

```json
{
  "id": 12345,
  "title": "Интерстеллар",
  "category": "Фильм",
  "description": "Когда засуха приводит человечество к продовольственному кризису...",
  "genres": ["фантастика", "драма", "приключения"],
  "rating": "8.6"
}
```

---

### `GET /api/rezka/info_movie`

**Источник:** `app/modules/rezka/router.py:44-49` → `RezkaService.info_movie` (`service.py:90-139`)

Полная карточка по **URL** страницы тайтла. Парсит страницу целиком: достаёт `movie_id` и `translator_id` из инициализатора плеера (`sof.tv.initCDNMoviesEvents` / `initCDNSeriesEvents`), определяет тип контента, рейтинги IMDb/КП, жанры и список переводов.

**Query-параметры**

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `movie_url` | `str` | да | URL карточки (поле `url` из поиска; принимается и относительный путь вида `/123-...html`, и абсолютный — внутри делается `URL.join`). |

**Ответ `200 OK`** — `InfoMovieResponse` (`schemas.py:32-42`):

| Поле | Тип | Описание |
|---|---|---|
| `id` | `int` | ID тайтла. |
| `title` | `str` | Название. |
| `alter_title` | `str \| null` | Оригинальное название. |
| `category` | `str` | Категория. |
| `description` | `str` | Описание. |
| `genres` | `list[str]` | Жанры. |
| `rating` | `dict[str, str] \| null` | Рейтинги по площадкам, ключи `"imdb"` и/или `"kp"` (`service.py:109-115`). Может быть пустым `{}`. |
| `url` | `str` | Эхо входного `movie_url`. |
| `content_type` | `str \| null` | `"movie"` или `"series"` (или `null`, если плеер не распознан, `service.py:97-107`). |
| `translators` | `dict[int, str \| null]` | Карта `translator_id → название перевода`. Значение может быть `null`. Если переводов нет, но известен один — `{translate_id: null}` (`service.py:119-126`). |

> Ключи `translators` в JSON станут строками (JSON не поддерживает целочисленные ключи объектов), хотя в Pydantic-схеме это `Dict[int, ...]`.

**Пример запроса**

```bash
curl "http://127.0.0.1:8000/api/rezka/info_movie?movie_url=https://rezka.ag/films/fantasy/12345-interstellar.html"
```

**Пример ответа**

```json
{
  "id": 12345,
  "title": "Интерстеллар",
  "alter_title": "Interstellar",
  "category": "Фильмы",
  "description": "Когда засуха приводит человечество к продовольственному кризису...",
  "genres": ["фантастика", "драма", "приключения"],
  "rating": { "imdb": "8.6", "kp": "8.6" },
  "url": "https://rezka.ag/films/fantasy/12345-interstellar.html",
  "content_type": "movie",
  "translators": { "238": "Дубляж", "56": "Профессиональный многоголосый" }
}
```

---

### `GET /api/rezka/movie_source`

**Источник:** `app/modules/rezka/router.py:52-58` → `RezkaStream.get_movie_source` (`service.py:143-152`)

Возвращает прямые ссылки на потоки фильма по качеству. Под капотом запрашивает `/ajax/get_cdn_series/` (`action=get_movie`) и декодирует обфусцированную строку через `StreamDecoder` (`_decoder.py`).

**Query-параметры**

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `movie_id` | `int` | да | ID фильма. |
| `translator_id` | `int` | да | ID перевода (из `translators` в `info_movie`). |

**Ответ `200 OK`** — `MovieResponse` (`schemas.py:45-46`):

| Поле | Тип | Описание |
|---|---|---|
| `urls` | `dict[str, str]` | Карта `качество → URL .mp4`. Ключи вида `"360p"`, `"480p"`, `"720p"`, `"1080p"`. |

> Декодер берёт только `.mp4`-ссылки и **исключает** вариант `"1080p Ultra"` (`_decoder.py:43-48`). Пустая входная строка приводит к `ValueError` → `500`.

**Пример запроса**

```bash
curl "http://127.0.0.1:8000/api/rezka/movie_source?movie_id=12345&translator_id=238"
```

**Пример ответа**

```json
{
  "urls": {
    "360p": "https://stream.example/.../360.mp4",
    "480p": "https://stream.example/.../480.mp4",
    "720p": "https://stream.example/.../720.mp4",
    "1080p": "https://stream.example/.../1080.mp4"
  }
}
```

---

### `GET /api/rezka/series_source`

**Источник:** `app/modules/rezka/router.py:61-69` → `RezkaStream.get_series_source` (`service.py:154-190`)

Возвращает структуру сезонов/эпизодов и ссылки на потоки конкретного эпизода. Под капотом — `/ajax/get_cdn_series/` (`action=get_episodes`).

**Query-параметры**

| Параметр | Тип | Обязательный | По умолчанию | Описание |
|---|---|---|---|---|
| `series_id` | `int` | да | — | ID сериала. |
| `translator_id` | `int` | да | — | ID перевода. |
| `season` | `int \| null` | нет | `None` | Номер сезона. Если не задан, Rezka вернёт дефолтный. |
| `episode` | `int \| null` | нет | `None` | Номер эпизода. Если не задан — дефолтный. |

> `season`/`episode` добавляются в запрос к Rezka только при «истинных» значениях (`if season:` / `if episode:`, `service.py:162-165`), поэтому `0` эквивалентно «не задано».

**Ответ `200 OK`** — `SeriesResponse` (`schemas.py:49-51`):

| Поле | Тип | Описание |
|---|---|---|
| `seasons` | `dict[int, list[int]]` | Карта `номер сезона → список ID эпизодов`. Парсинг сезонов устойчив к локализации (regex по числу, `service.py:21,176-179`). |
| `urls` | `dict[str, str]` | Карта `качество → URL .mp4` для выбранного (или дефолтного) эпизода — формат тот же, что и у `movie_source`. |

> Как и для целочисленных ключей выше, в JSON ключи `seasons` сериализуются строками.

**Пример запроса**

```bash
curl "http://127.0.0.1:8000/api/rezka/series_source?series_id=67890&translator_id=56&season=1&episode=3"
```

**Пример ответа**

```json
{
  "seasons": {
    "1": [1, 2, 3, 4, 5, 6, 7, 8],
    "2": [1, 2, 3, 4, 5, 6]
  },
  "urls": {
    "480p": "https://stream.example/.../s1e3-480.mp4",
    "720p": "https://stream.example/.../s1e3-720.mp4",
    "1080p": "https://stream.example/.../s1e3-1080.mp4"
  }
}
```

---

## Сквозные примечания и подводные камни

- **In-memory состояние.** Все комнаты живут в одном словаре singleton-сервиса `RoomService` (`service.py:5-7`, `dependencies.py:3`). Перезапуск процесса = потеря всех комнат. Персистентности (Redis/БД) нет — это сознательное ограничение проекта.
- **Автоудаления пустых комнат нет.** Комнаты удаляются только вручную через `DELETE`. При этом удалить комнату с активными WS-участниками нельзя (`409`).
- **Статус не редактируется через REST.** `status` — производное от `is_paused`/`is_loaded`, которыми управляет только WebSocket-обработчик (`app/modules/room/handler.py`). См. отдельный документ по WS-протоколу.
- **Целочисленные ключи в JSON.** `translators` (`info_movie`) и `seasons` (`series_source`) описаны как `Dict[int, ...]`, но в JSON их ключи будут строками.
- **Rezka хрупок.** Парсинг завязан на HTML-структуру `rezka.ag`. При изменении вёрстки эндпоинты Rezka могут начать отдавать пустые поля или `500`. Все ошибки сети/HTTP от Rezka превращаются в `500`.
- **`/redirect` использует код 307**, а не 302 — метод запроса сохраняется. Для прохода по ссылке в `curl` нужен флаг `-L`.

---

## Развёртывание (актуальное состояние)

> Этот раздел отражает **реальные конфиги в репозитории**, а не устаревший корневой `DOCUMENTATION.md`.

- **`docker-compose.yml` содержит ОДИН сервис** — `sync-mate-api-ws` (`docker-compose.yml:1-8`). Отдельного сервиса `cloudflared` больше нет (удалён в коммите `f0c7443`). Порт публикуется как `${SERVER_PORT:-8000}:8000`.
- **Образ:** собирается из `Dockerfile` на базе `python:3.13-slim`, запускается командой `uvicorn app.main:app --host 0.0.0.0 --port 8000` (`Dockerfile:1,16`). Публикуется в `ghcr.io/zebaro24/sync-mate-api-ws`.
- **CI (`.github/workflows/ci.yml`) тестирует ТОЛЬКО на Python 3.13.** Матрицы версий нет — все джобы (`Lint & Format`, `Type Checking`, `Security Audit`, `Tests & Coverage`) поднимают `python-version: '3.13'`. (Бейдж в `README.md` и `CLAUDE.md` упоминают «3.11+» — это только нижняя граница совместимости, не матрица CI.)
- **CD (`.github/workflows/cd.yml`)** срабатывает на тег `v*`: собирает и пушит Docker-образ в GHCR, затем по SSH копирует `docker-compose.yml` на сервер и выполняет `docker compose -p sync-mate up -d --pull always`. Окружение `prod` → `https://sync-mate-api-ws.zebaro.dev`.

### Имена переменных окружения

> Значения секретов не приводятся. Файл `.env` не читать и не коммитить.

Переменные, читаемые приложением (`app/config.py`, через `pydantic-settings`; имена регистронезависимы):

| Переменная | Назначение | Значение по умолчанию |
|---|---|---|
| `APP_NAME` | Имя сервиса (в `/api/info`, заголовке OpenAPI). | `"Sync-Mate-API-WS"` |
| `DESCRIPTION` | Описание сервиса. | см. `config.py:6-11` |
| `AUTHOR` | Автор. | `"Zebaro (zebaro.dev)"` |
| `VERSION` | Версия. | `"0.1.1"` |
| `DEBUG` | Режим отладки (уровень логов, `FastAPI(debug=...)`). | `False` |
| `REQUIRED_DOWNLOAD_TIME` | Сколько секунд буфера нужно каждому участнику для готовности комнаты. | `15` |
| `REZKA_URL` | Базовый URL Rezka. | `"https://rezka.ag"` |
| `PROXIES_LIST` | CSV-список прокси для запросов к Rezka (парсится в список в `config.py:25-28`). | `None` |

Переменные окружения для развёртывания (вне `Settings`):

| Переменная | Где используется |
|---|---|
| `SERVER_PORT` | Публикуемый порт хоста в `docker-compose.yml:8`. |

CI/CD-секреты GitHub Actions (имена): `SERVER_HOST`, `SERVER_USER`, `SSH_PRIVATE_KEY`, `PROXIES_LIST`, `GITHUB_TOKEN`, переменная окружения `vars.SERVER_PORT`.

> В репозиторном `.env` может оставаться легаси-переменная `CLOUDFLARE_TUNNEL_TOKEN` от прежней схемы с туннелем — приложением и текущим `docker-compose.yml` она **не используется** (сервис `cloudflared` удалён).

---

## См. также

- [`../CLAUDE.md`](../CLAUDE.md) — гид по бэкенд-части (стек, слои, race conditions, конвенции).
- [`../../CLAUDE.md`](../../CLAUDE.md) — корневой гид по монорепозиторию Sync-Mate.
- [`../../Sync-Mate-Extension/CLAUDE.md`](../../Sync-Mate-Extension/CLAUDE.md) — гид по браузерному расширению (клиент этого API).
- [`../../DOCUMENTATION.md`](../../DOCUMENTATION.md) — полная техническая документация и описание WS-протокола (внимание: раздел про деплой частично устарел — доверяйте конфигам в коде).
- WebSocket-протокол (`/ws/{room_id}`): `app/ws/router.py` + `app/modules/room/handler.py` — синхронизация `play`/`pause`/`seek`/буферизации между участниками.
