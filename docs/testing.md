# Тестирование (Sync-Mate-API-WS)

Полное руководство по тестам бэкенда: как устроен набор тестов, по каким правилам он пишется, как мокаются HTTP и WebSocket и — главное — как всё это **правильно запускать через gate**, а не голым `pytest`.

> TL;DR. Не запускайте `pytest` руками. Единственный санкционированный способ — `python scripts/gate.py`:
> ```bash
> # из корня репозитория-обёртки (D:\Projects\Sync-Mate)
> python scripts/gate.py --repo api --tests          # весь pytest
> python scripts/gate.py --repo api --strict          # + покрытие (порог 85%)
> python scripts/gate.py --repo api --only pytest -- tests/ws/test_websocket.py   # точечно
> ```
> Сейчас в наборе **54 теста**, строчное покрытие `app/` ≈ **88 %** при «полу» (floor) **85 %**.

---

## 1. Где что лежит: структура зеркалит `app/`

Каталог `tests/` повторяет дерево `app/` — для каждого модуля приложения есть параллельный модуль тестов. Это не формальность: при добавлении кода в `app/` ищите/создавайте тест в зеркальном месте `tests/`.

| Тест | Покрывает в `app/` | Что именно |
|---|---|---|
| `tests/api/test_endpoints.py` | `app/api/router.py`, `app/main.py`, REST-роутеры модулей | HTTP-эндпоинты через `TestClient` |
| `tests/services/rezka/test_rezka_base.py` | `app/modules/rezka/_base.py` | `RezkaBase`: прокси, `_parse_response`, `get`/`post`, `_request`, `get_text` |
| `tests/services/rezka/test_rezka_decoder.py` | `app/modules/rezka/_decoder.py` | `StreamDecoder.decode` / `_decode_stream_base64` |
| `tests/services/rezka/test_rezka_service.py` | `app/modules/rezka/service.py` (`RezkaService`) | `quick_search`, `quick_info_movie`, `search`, `info_movie` |
| `tests/services/rezka/test_rezka_stream.py` | `app/modules/rezka/service.py` (`RezkaStream`) | `get_movie_source`, `get_series_source` |
| `tests/services/room/test_room.py` | `app/modules/room/models.py` (`Room`) | `add_user`/`remove_user`, `check_is_loaded`, `play`/`pause`/`seek`, `load` |
| `tests/services/room/test_room_storage.py` | `app/modules/room/service.py` (`RoomService`) | `create_room`/`get_room`/`delete_room` |
| `tests/services/room/test_user_handler.py` | `app/modules/room/handler.py` (`UserHandler`) | диспетчеризация WS-действий, `_broadcast`, `_handle_*` |
| `tests/ws/test_websocket.py` | `app/ws/router.py` | жизненный цикл WS-соединения (`websocket_endpoint`) |

Вспомогательные файлы:

| Файл | Назначение |
|---|---|
| `tests/conftest.py` | автоочистка глобального `RoomService._storage` между тестами (см. §2) |
| `tests/client.py` | общий экземпляр `TestClient(app)` для HTTP-тестов (см. §3) |

### Импорты и namespace-пакеты

В каталогах `tests/**` **нет** файлов `__init__.py`. Импорты вида `from tests.client import client` (`tests/api/test_endpoints.py:1`) и `from app.modules...` работают за счёт строки `pythonpath = ["."]` в `pyproject.toml` (`pyproject.toml:111`): корень репозитория попадает в `sys.path`, а `tests` и `app` подхватываются как implicit namespace packages. Поэтому имена тест-файлов держим уникальными во всём дереве — при `prepend`-режиме импорта pytest совпадение имён без `__init__.py` приводит к коллизиям модулей.

---

## 2. `tests/conftest.py` — изоляция глобального состояния

`RoomService` хранит комнаты в in-memory `dict`, а через `app/modules/room/dependencies.py` существует **единственный синглтон** `_room_service`. Без сброса состояние протекало бы между тестами.

```python
# tests/conftest.py
import pytest
from app.modules.room.dependencies import _room_service

@pytest.fixture(autouse=True)
def _reset_room_storage():
    """Изолирует тесты, использующие глобальный RoomService."""
    _room_service._storage.clear()
    yield
    _room_service._storage.clear()
```

Ключевые свойства:

- `autouse=True` — фикстура применяется ко **всем** тестам автоматически, её не нужно запрашивать в аргументах.
- Чистится **дважды** — до (`clear()` перед `yield`) и после (`clear()` после `yield`). Это защищает и от «грязи», оставленной предыдущим запуском в том же процессе, и от утечки наружу.
- Очищается именно тот объект, который видит приложение: импортируется ровно `_room_service` из `dependencies`, а не новый `RoomService()`. WS- и REST-роутеры берут сервис через `Depends(get_room_service)`, который возвращает этот же синглтон.

> Важно: большинство юнит-тестов `Room`/`RoomService`/`UserHandler` создают **локальные** объекты (`Room(...)`, `RoomService()`) и от синглтона не зависят. Фикстура страхует те случаи, где запрос идёт через `TestClient` и реальный `Depends`-граф (HTTP-роутеры комнат).

---

## 3. `tests/client.py` — HTTP-клиент

```python
# tests/client.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
```

`TestClient` (на базе httpx) поднимает приложение in-process, без реального сетевого сокета. Используется в `tests/api/test_endpoints.py`:

```python
from tests.client import client

def test_info():
    response = client.get("/api/info")
    assert response.status_code == 200
    assert response.json().get("name") == "Sync-Mate-API-WS"
```

`TestClient` умеет и WebSocket (`client.websocket_connect(...)`), но WS-уровень здесь тестируется иначе — напрямую через корутину `websocket_endpoint` с мок-сокетом (см. §6), что быстрее и точнее изолирует логику роутера.

---

## 4. Конфигурация pytest (`[tool.pytest.ini_options]`)

Вся конфигурация — в `pyproject.toml:109-126`. Разберём построчно, потому что почти каждый флаг влияет на то, как писать тесты.

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = [
    "--verbose",
    "--color=yes",
    "--strict-markers",
    "--strict-config",
    "--rootdir=.",
]
filterwarnings = [
    "error",
    "ignore::DeprecationWarning",
]
markers = [
    "asyncio: mark test as asyncio",
    "slow: mark test as slow",
]
```

| Опция | Значение | Следствие для автора тестов |
|---|---|---|
| `testpaths = ["tests"]` | сбор только из `tests/` | новые тесты кладём строго под `tests/**` |
| `pythonpath = ["."]` | корень в `sys.path` | работают импорты `app.*` и `tests.*` (см. §1) |
| `--strict-markers` | неизвестный маркер = ошибка | любой `@pytest.mark.<x>` обязан быть объявлен в `markers` |
| `--strict-config` | опечатка/неизвестный ключ в конфиге = ошибка | конфиг pytest нельзя «тихо» сломать |
| `filterwarnings = ["error", ...]` | предупреждения = падение | код и тесты должны быть «чистыми» по варнингам |
| `markers = [...]` | объявлены `asyncio`, `slow` | только эти маркеры разрешены |

### 4.1. `--strict-markers` + объявленный маркер `asyncio`

Здесь маркер `asyncio` объявлен в `markers` **вручную**, а не предоставлен плагином автоматически. Это согласуется с тем, что режим автодетекта **выключен** (см. §5). Если бы маркера не было в списке — `@pytest.mark.asyncio` падал бы из-за `--strict-markers`.

Маркер `slow` объявлен на будущее (помечать долгие тесты), но в текущем наборе не используется.

### 4.2. `filterwarnings = error` — варнинги ломают сборку

Любой `Warning`, всплывший во время теста, превращается в исключение и **роняет** тест. Единственное исключение — `DeprecationWarning` (`ignore::DeprecationWarning`), который намеренно глушится, чтобы зависимости-устаревайки не валили набор.

Практические следствия:

- Нельзя оставлять «спящие» корутины: если вы создали `AsyncMock`/корутину и не сделали `await`/`assert_awaited`, Python выдаст `RuntimeWarning: coroutine ... was never awaited` → тест упадёт.
- Любой `ResourceWarning`, `PytestUnraisableExceptionWarning` и т. п. — это red, а не yellow. Чините причину, не глушите.

### 4.3. `--strict-config`

Опечатка в `[tool.pytest.ini_options]` (например, неизвестный ключ) приводит к ошибке запуска, а не к молчаливому игнорированию. Меняя конфиг, прогоняйте gate — он сразу покажет проблему.

---

## 5. Правило `@pytest.mark.asyncio` — ставится ЯВНО

`asyncio_mode = "auto"` **сознательно НЕ включён**. Это значит:

> Каждый `async def test_...` обязан быть помечен декоратором `@pytest.mark.asyncio`. Без него `pytest-asyncio` не подхватит корутину — тест либо будет пропущен, либо упадёт с предупреждением о невыполненной корутине (а из-за `filterwarnings=error` — именно упадёт).

Канонический вид (см. `tests/ws/test_websocket.py:11`, `tests/services/room/test_room.py:27`):

```python
import pytest

@pytest.mark.asyncio
async def test_play_sends_play_to_all(mock_user):
    room = Room("1", "Room1", "video.mp4", 0, created_at="now")
    await room.add_user(mock_user)
    await room.play()
    mock_user.websocket.send_json.assert_awaited_once_with({"type": "play"})
```

Синхронные тесты декоратор **не** получают — например `test_load_sets_state_correctly` (`tests/services/room/test_room.py:61`) и весь `tests/services/rezka/test_rezka_decoder.py` (декодер синхронный). Проверяйте каждую сигнатуру: `async def` → нужен `@pytest.mark.asyncio`; обычный `def` → нет.

Почему явный режим, а не `auto`: чистый барьер между sync- и async-тестами (декодер, `_get_random_proxy`, `_parse_response` — синхронные), плюс отсутствие «магии», когда забытый `await` в обычной функции внезапно «работает».

---

## 6. Паттерн моков HTTP (httpx)

Бэкенд ходит на rezka.ag через `httpx.AsyncClient`, обёрнутый в `RezkaBase.get` / `RezkaBase.post` (`app/modules/rezka/_base.py`). В тестах сервисов **сеть не трогаем** — подменяем уже распарсенный результат на уровне метода `get`/`post`:

```python
mocker.patch.object(service, "post", AsyncMock(return_value=soup))
# или
mocker.patch.object(service, "get", AsyncMock(return_value=soup))
```

Ключевые моменты паттерна (см. `tests/services/rezka/test_rezka_service.py`):

1. **`mocker`** — фикстура `pytest-mock`, не нужно ничего импортировать вручную.
2. **`AsyncMock`** — потому что `get`/`post` — корутины; обычный `MagicMock` вернул бы не-awaitable и при `await` дал бы ошибку.
3. **`return_value`** — это уже «готовый» результат `_parse_response`: либо `BeautifulSoup` (для HTML-методов), либо `dict` (для JSON-методов вроде `get_movie_source`). То есть мокаем по контракту `get`/`post`, а не сырой `Response`.
4. **`mocker.patch.object(service, ...)`** — патчим **экземпляр** из фикстуры `service` (`RezkaService()` / `RezkaStream()`), а не класс. Изоляция между тестами гарантирована тем, что `service` создаётся заново каждым тестом.

Где какой метод мокать:

| Метод сервиса | Мокать | Тип `return_value` |
|---|---|---|
| `quick_search`, `quick_info_movie` | `post` | `BeautifulSoup` |
| `search`, `info_movie` | `get` | `BeautifulSoup` |
| `get_movie_source`, `get_series_source` | `post` | `dict` (`{"url": ..., "seasons": ..., "episodes": ...}`) |

Поверх можно подменять и внутренний декодер, чтобы не гонять реальный base64:

```python
mocker.patch.object(StreamDecoder, "decode", return_value={"720p": "url1.mp4"})
```

(см. `tests/services/rezka/test_rezka_stream.py:19`).

### 6.1. Тест на уровне транспорта `RezkaBase`

Когда нужно проверить сам HTTP-слой (а не парсинг), мокается слой ниже — либо `RezkaBase._request`, либо целиком `httpx.AsyncClient`:

- Подмена `_request` (`tests/services/rezka/test_rezka_base.py:42-66`): `mocker.patch.object(RezkaBase, "_request", AsyncMock(return_value=...))`, далее проверка `mock_request.assert_awaited_once()` и проброса результата.
- Подмена `httpx.AsyncClient` целиком (`tests/services/rezka/test_rezka_base.py:69-97`): фейковый async-контекст-менеджер с `request()`, чей `raise_for_status()` кидает `httpx.HTTPStatusError`. Тест проверяет, что `_request` пробрасывает `httpx.HTTPError`. Это и есть «контракт ошибок»: сетевые сбои rezka.ag должны подниматься наверх (→ 500), а не глохнуть.

### 6.2. Парсинг через `BeautifulSoup`

HTML-фикстуры объявляются модульными константами (`HTML_QUICK_SEARCH`, `HTML_INFO` и т. д. в `tests/services/rezka/test_rezka_service.py:8-50`) и оборачиваются в `BeautifulSoup(html, "html.parser")`. Покрыты и «грязные» сценарии: элемент без числового id (`test_quick_search_skips_items_without_id`), пустой HTML (`test_quick_info_movie_handles_empty_response`), локализованные названия сезонов «Сезон N» вместо «Season N» (`test_get_series_source_with_localized_season_names`).

---

## 7. Паттерн WS-тестов (`SimpleNamespace` + `AsyncMock`)

WS-роутер (`app/ws/router.py`) тестируется **без реального WebSocket** — корутина `websocket_endpoint` вызывается напрямую, а зависимости подставляются вручную. Это позволяет точно управлять последовательностью входящих сообщений и проверять каждое ребро жизненного цикла.

Шаблон фейкового сокета (`tests/ws/test_websocket.py:16-22`):

```python
from types import SimpleNamespace
from typing import Any

mock_ws: Any = SimpleNamespace(
    client="127.0.0.1",
    accept=mocker.AsyncMock(),
    close=mocker.AsyncMock(),
    send_json=mocker.AsyncMock(),
    receive_json=mocker.AsyncMock(side_effect=side_effect),
)
```

Почему так:

- **`SimpleNamespace`** — лёгкая «утиная» замена `WebSocket`: задаём ровно те атрибуты/методы, которые трогает роутер (`accept`, `close`, `send_json`, `receive_json`, `client`). Не нужно конструировать настоящий Starlette-`WebSocket`.
- **`mocker.AsyncMock()`** на каждый async-метод сокета — все они await-ятся в роутере.
- **`receive_json=AsyncMock(side_effect=[...])`** — это сердце паттерна: `side_effect`-список разыгрывает поток сообщений по одному на каждый `await receive_json()`.
- **`# type: ignore`-эквивалент** — аннотация `mock_ws: Any`, чтобы mypy не ругался на подмену типа `WebSocket`.

### 7.1. Как завершают бесконечный цикл

Роутер крутит `while True: data = await receive_json(); await handler.handle(data)` (`app/ws/router.py:42-44`). Чтобы выйти из него в тесте, последним элементом `side_effect` кладут **исключение**:

```python
messages = [{"type": "connect", "name": "TestUser"}, {"type": "info"}]
side_effect = messages + [asyncio.CancelledError()]
...
with pytest.raises(asyncio.CancelledError):
    await websocket_endpoint(mock_ws, "room123", room_service=mock_service)
```

`asyncio.CancelledError` пробивает `except Exception` роутера (в Python 3.8+ это `BaseException`, не ловится `except Exception`), долетает до теста и одновременно гарантирует, что `finally: await room.remove_user(user)` отработал. После этого делаются проверки:

```python
mock_ws.accept.assert_awaited_once()
mock_room.add_user.assert_awaited_once()
mock_ws.send_json.assert_awaited_with({"type": "connect", "id": ANY})
mock_room.remove_user.assert_awaited_once()
```

`ANY` из `unittest.mock` — потому что `user_id` это случайный uuid.

### 7.2. Мок комнаты и сервиса

```python
mock_room = SimpleNamespace(add_user=mocker.AsyncMock(), remove_user=mocker.AsyncMock())
mock_service = MagicMock()
mock_service.get_room.return_value = mock_room          # или None — комната не найдена
mocker.patch("app.ws.router.UserHandler.handle", new=mocker.AsyncMock())
```

- `mock_service` — обычный `MagicMock` (его `get_room` синхронный), возвращает либо мок-комнату, либо `None`.
- `UserHandler.handle` патчится **по пути импорта в роутере** (`app.ws.router.UserHandler.handle`), а не по месту определения — иначе подмена не подхватится. Логика самого `handle` проверяется отдельно в `tests/services/room/test_user_handler.py`.

### 7.3. Сценарии, покрытые в `tests/ws/test_websocket.py`

| Тест | Что проверяет | Ожидаемое поведение роутера |
|---|---|---|
| `test_websocket_successful_connection` | happy path: connect → info → отмена | `accept`, `add_user`, ответ `{"type":"connect","id":ANY}`, `remove_user` в `finally` |
| `test_room_not_found` | `get_room` вернул `None` | `close(code=4000, reason="Room not found")`, ранний `return` |
| `test_invalid_connection_message` | первое сообщение не `connect` | `close(code=4001, reason="Authentication is required")` |
| `test_exception_in_handle` | `handle` бросает `Exception` | `close(code=1011)` + `remove_user` |
| `test_multiple_messages` | connect + info + status | `handle` вызван **2 раза** (connect не считается), `remove_user` |

Эти пять кейсов соответствуют четырём «выходам» роутера: 4000 (нет комнаты), 4001 (нет аутентификации), 1011 (внутренняя ошибка) и нормальный цикл с гарантированным `remove_user` в `finally`.

---

## 8. Паттерн юнит-тестов `Room` / `RoomService` / `UserHandler`

### 8.1. `Room` (`tests/services/room/test_room.py`)

- **`mock_settings` (autouse, локальная)**: подменяет `app.modules.room.models.settings` на `MagicMock` с `REQUIRED_DOWNLOAD_TIME = 5`, чтобы тест не зависел от реального `.env` (`tests/services/room/test_room.py:8-13`). Патчится по пути импорта в `models`.
- **`mock_user`**: `MagicMock` с вложенным `websocket = AsyncMock()`; `send_json` тем самым awaitable и проверяется через `assert_awaited_once_with({...})`.
- Реальные объекты `Room(...)` создаются прямо в тесте; конструктор: `Room(room_id, name, video_url, current_time, created_at=...)`.
- Проверяется доменная логика: идемпотентность `remove_user` (`test_remove_user_is_idempotent` — повторный вызов не должен кидать `ValueError`), пороговая логика `check_is_loaded` (true при `downloaded_time >= REQUIRED_DOWNLOAD_TIME`, false иначе), адресация рассылок (`play` всем; `pause`/`seek` всем кроме `exception_user`; `seek(..., user=...)` — конкретному пользователю).

### 8.2. `RoomService` (`tests/services/room/test_room_storage.py`)

- Фикстура `room_schema` — `MagicMock`, чей `model_dump()` возвращает dict полей комнаты (имитация Pydantic-схемы без её конструирования).
- Покрывает `create_room`, `get_room` (есть/нет), и правило удаления: `delete_room` возвращает `True` и удаляет только если `user_storage` пуст; при наличии пользователей — `False`, комната остаётся.

### 8.3. `UserHandler` (`tests/services/room/test_user_handler.py`)

- `room = MagicMock()`, на нужные async-методы навешивается `AsyncMock` точечно (`room.play = AsyncMock()`, `room.check_is_loaded = AsyncMock(return_value=True)` и т. д.). Синхронные (`room.load`) остаются обычным `MagicMock` и проверяются `assert_called_once_with`.
- Проверяется диспетчер `handle`: маршрутизация по `type`, обновление `user.info` для `info`, цепочки `_handle_play`/`_handle_pause`/`_handle_status`/`_handle_load`, игнор `set_video` без `video_url` и игнор неизвестного `type` (`_VALID_ACTIONS`, `app/modules/room/handler.py:10`).
- `_broadcast` проверяется через `room.get_users_exc.return_value = [...]`: рассылка уходит всем, кроме автора.

> Соглашение проекта: любое новое действие в `_VALID_ACTIONS` обязано иметь и `_handle_*`, и тест в `test_user_handler.py` — иначе действие «молча принимается» без эффекта (исторический баг, см. `CLAUDE.md` бэкенда).

---

## 9. Как запускать: ТОЛЬКО через gate

`scripts/gate.py` — единственный санкционированный раннер для обоих подпроектов. Он сам вызывает `poetry run pytest` с нужными флагами, ловит вывод и печатает компактную таблицу pass/fail. **Не вызывайте `pytest`, `mypy`, `black` руками** — gate гарантирует те же флаги, что и CI, и считает покрытие.

### 9.1. Базовые команды

```bash
# из корня репозитория-обёртки D:\Projects\Sync-Mate
python scripts/gate.py --repo api              # core: все линтеры + pytest (без покрытия)
python scripts/gate.py --repo api --tests      # только тесты (pytest)
python scripts/gate.py --repo api --lint       # только статические проверки
python scripts/gate.py --repo api --strict     # + heavy-проверки, в т.ч. coverage
python scripts/gate.py --repo api --list       # показать все проверки и выйти
```

Алиасы репозитория: `api` == `backend` == `be`. Если запускать из каталога `Sync-Mate-API-WS`, `--repo` можно опустить — gate выведет repo из имени папки.

### 9.2. Точечный прогон одного теста/файла

Чтобы прогнать конкретный путь, выбираем единственную проверку `pytest` через `--only` и передаём аргументы после `--`:

```bash
# один файл
python scripts/gate.py --repo api --only pytest -- tests/ws/test_websocket.py

# один тест по узлу
python scripts/gate.py --repo api --only pytest -- tests/services/room/test_room.py::test_play_sends_play_to_all

# по подстроке имени
python scripts/gate.py --repo api --only pytest -- -k "loaded"
```

Механика (см. `scripts/gate.py:128-198`): всё после `--` отрезается как `passthrough` и **дописывается к последнему шагу выбранной проверки**. Поэтому passthrough работает только когда выбрана **ровно одна** проверка — иначе gate напечатает `note: extra args after \`--\` need exactly one check ...` и проигнорирует аргументы. Отсюда обязательный `--only pytest`.

### 9.3. Состав проверок репозитория `api`

Перечень из `scripts/gate.py:56-72` (группа / core|strict):

| Имя | Команда | Группа | По умолчанию? |
|---|---|---|---|
| `black` | `poetry run black --check app tests` | lint | core |
| `isort` | `poetry run isort --check-only app tests` | lint | core |
| `flake8` | `poetry run flake8 app tests` | lint | core |
| `mypy` | `poetry run mypy app` | lint | core |
| `bandit` | `poetry run bandit -q -c pyproject.toml -r app` | lint | core |
| `arch` | `scripts/arch_lint_api.py` | lint | core |
| `protocol` | `scripts/protocol_sync.py` | lint | core |
| `pytest` | `poetry run pytest -q` | test | core |
| `coverage` | `pytest --cov=app --cov-report=json` + `scripts/coverage_gate.py` | test | **strict** |

`--tests` оставляет только группу `test` (`pytest`, плюс `coverage` при `--strict`). `--lint` — только статику. `--strict`/`--full` добавляет heavy-проверки (здесь — `coverage`).

> `safety check` **намеренно не входит** в gate (deprecated, требует коммерческой лицензии, висит/падает headless). SAST покрыт `bandit`, а CVE-сканирование зависимостей остаётся в CI. Это расхождение со старой документацией — доверяйте коду gate.

---

## 10. Покрытие

- Считается отдельной strict-проверкой `coverage`: сперва `poetry run pytest --cov=app --cov-report=json -q`, затем `scripts/coverage_gate.py` сверяет `coverage.json` с порогом.
- **Порог (floor) = 85.0 %** — это «ratchet» (`scripts/coverage_gate.py:24`): поднимаем по мере роста, не опускаем без причины. Переопределяется флагом `--floor N` или переменной окружения `COVERAGE_FLOOR`.
- Текущее строчное покрытие `app/` ≈ **88 %** (замер 2026-06). Порог стоит чуть ниже, чтобы ловить регрессии, не падая на шуме.
- Что исключено из подсчёта — секция `[tool.coverage.run]`/`[tool.coverage.report]` в `pyproject.toml:131-153`: сами тесты, `version.py`/`setup.py`, а из строк — `def __repr__`, `if settings.DEBUG`, `raise NotImplementedError`, `@abstractmethod`, `if __name__ == "__main__":` и т. п. Для одноразовых исключений используйте `# pragma: no cover` (так помечен, например, заведомо недостижимый `json()` в фейковом ответе — `tests/services/rezka/test_rezka_base.py:81`).

Запуск:

```bash
python scripts/gate.py --repo api --strict                  # покрытие как часть полного прогона
python scripts/gate.py --repo api --only coverage           # только покрытие
```

При прохождении gate печатает строку-итог даже на success (имя `coverage` в `SHOW_OUTPUT_ON_PASS`, `scripts/gate.py:87`):
`coverage gate: ✓ total 88.x% (floor 85.0%)`.

---

## 11. CI

CI (`.github/workflows/ci.yml`) гоняет четыре независимых job: `lint-format`, `type-check`, `security`, `test`. Ключевые факты:

- **Только Python 3.13.** Матрицы версий нет — все job используют `python-version: '3.13'`. (Несмотря на `python = "^3.11"` в `pyproject.toml` и target `py311` у black — это нижняя граница совместимости, а не версия CI.)
- Job `test` запускает `poetry run pytest --cov=app --cov-report=xml --cov-report=term-missing` и заливает `coverage.xml` в Codecov (`fail_ci_if_error: true`).
- Окружение теста задаёт `PYTHONPATH: .` и секрет `PROXIES_LIST`.
- В CI всё ещё присутствует шаг `Run Safety` (job `security`), хотя в локальном gate `safety` сознательно отключён — при работе локально опирайтесь на gate.

Локальный gate ≈ зеркало CI по линтерам/типам/тестам, но удобнее: одна команда, единая таблица, встроенный coverage-ratchet.

---

## 12. Гочи и типичные ошибки

- **Забыли `@pytest.mark.asyncio` на `async def`** — тест не выполнится корректно, а из-за `filterwarnings=error` упадёт по `RuntimeWarning` о невыполненной корутине. Режим `auto` выключен намеренно.
- **`MagicMock` вместо `AsyncMock` для awaitable** — `await mock()` вернёт не-awaitable → ошибка. Для `send_json`/`get`/`post`/`add_user`/`check_is_loaded` и пр. всегда `AsyncMock`.
- **Патч не по тому пути** — патчить нужно там, где имя используется (`app.ws.router.UserHandler.handle`, `app.modules.room.models.settings`), а не там, где определено.
- **Незавершённый `side_effect` у `receive_json`** в WS-тестах — если список сообщений кончится без терминирующего исключения, `AsyncMock` бросит `StopIteration`/`StopAsyncIteration`; кладите в хвост `asyncio.CancelledError()` (или `Exception`) и оборачивайте вызов в `pytest.raises(...)` там, где это уместно.
- **Любой варнинг — это падение.** Не глушите варнинг локально; устраняйте причину (исключение `DeprecationWarning` уже сделано глобально).
- **Запуск `pytest` руками** не учитывает порог покрытия и может разойтись с CI по флагам. Гоняйте через gate.
- **Новые тест-файлы с неуникальными именами** при отсутствии `__init__.py` могут коллизировать на импорте — давайте файлам уникальные имена в пределах `tests/`.
- **Не полагайтесь на порядок тестов** относительно глобальной комнаты — `conftest._reset_room_storage` чистит синглтон до и после каждого теста.

---

## См. также

- [`../CLAUDE.md`](../CLAUDE.md) — гид по бэкенду (раздел «Тесты» — краткая версия этого документа).
- [`../../CLAUDE.md`](../../CLAUDE.md) — общий гид по репозиторию Sync-Mate (конвенции, что не делать).
- [`../../DOCUMENTATION.md`](../../DOCUMENTATION.md) — полная техническая документация и WS-протокол (контракт, который проверяют WS/handler-тесты). Внимание: раздел про деплой частично устарел — доверяйте коду `docker-compose.yml`/CI, а не доку.
- [`../../Sync-Mate-Extension/CLAUDE.md`](../../Sync-Mate-Extension/CLAUDE.md) — фронтенд-часть; тесты расширения гоняются через тот же gate (`--repo ext`).
- `scripts/gate.py`, `scripts/coverage_gate.py` — исходники раннера и ratchet-проверки покрытия.
- `.claude/docs/conventions.md` — авторитетный референс по конвенциям gate.
