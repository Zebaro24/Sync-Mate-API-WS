# Конвенции бэкенда Sync-Mate-API-WS

Полный и окончательный справочник по код-стилю, инструментам качества, структурным
правилам и списку «что НЕ делать» для FastAPI + WebSocket-сервера. Источник истины —
сами конфиги (`pyproject.toml`) и скрипты `scripts/*.py`; этот документ их объясняет,
а не заменяет.

---

## 0. Главное правило: все проверки идут через `gate.py`

Никаких ручных вызовов `pytest` / `mypy` / `black` / `isort` / `flake8` / `bandit` в
основной сессии. Единственный санкционированный способ запустить проверки бэкенда:

```bash
python scripts/gate.py --repo api            # core: lint + type + arch + protocol + tests
python scripts/gate.py --repo api --lint     # только статические проверки
python scripts/gate.py --repo api --tests    # только тесты
python scripts/gate.py --repo api --strict   # + тяжёлые: coverage
python scripts/gate.py --repo api --only mypy
python scripts/gate.py --repo api --only pytest -- tests/services/room/test_room.py
python scripts/gate.py --repo api --list     # перечислить все проверки и выйти
```

Алиасы репозитория: `backend` / `be` == `api` (`scripts/gate.py:44`). Если `--repo` не
передан, gate пытается определить репозиторий по имени текущей папки (`scripts/gate.py:150-155`).

### Состав core-проверок `api` (`scripts/gate.py:56-72`)

| Проверка | Команда | Группа | Когда запускается |
|---|---|---|---|
| `black` | `black --check app tests` | lint | всегда |
| `isort` | `isort --check-only app tests` | lint | всегда |
| `flake8` | `flake8 app tests` | lint | всегда |
| `mypy` | `mypy app` | lint | всегда |
| `bandit` | `bandit -q -c pyproject.toml -r app` | lint | всегда |
| `arch` | `python scripts/arch_lint_api.py` | lint | всегда |
| `protocol` | `python scripts/protocol_sync.py` | lint | всегда |
| `pytest` | `pytest -q` | test | всегда |
| `coverage` | `pytest --cov=app --cov-report=json` → `coverage_gate.py` | test | только `--strict` |

Многошаговая проверка падает на первом упавшем шаге (`scripts/gate.py:98-110`). `coverage`
и `protocol` печатают свою сводку даже при успехе (`SHOW_OUTPUT_ON_PASS`,
`scripts/gate.py:87`). Exit-код gate: `0` — всё прошло, `1` — есть падения, `2` — плохие
аргументы.

> Внимание: `safety check` **сознательно не входит** в gate (`scripts/gate.py:67-69`) —
> инструмент задепрекейчен, требует коммерческой лицензии для ремедиации и в headless-режиме
> постоянно «ноет»/падает. SAST покрыт `bandit`; CVE-сканирование зависимостей остаётся в CI
> (`.github/workflows/ci.yml`) либо переезжает на `pip-audit`.

### Структурные правила проверяет `arch_lint_api.py`

`scripts/arch_lint_api.py` (чистый stdlib, regex/AST, низкий процент ложных срабатываний)
проверяет три инварианта: направление слоёв, паритет `_VALID_ACTIONS` ↔ обработчик и
запрет синхронного HTTP. Подробности — в разделах [§7](#7-направление-слоёв-layer-direction),
[§8](#8-паритет-_valid_actions--обработчик) и [§9](#9-только-async-http-httpxasyncclient).

---

## 1. Форматирование — Black

Конфиг: `pyproject.toml:42-54`.

```toml
[tool.black]
line-length = 120
target-version = ["py311"]
include = '\.pyi?$'
extend-exclude = '/(\.eggs | \.git | \.venv | build | dist)/'
```

- **Длина строки — 120** символов (не дефолтные 88). Это сквозное значение: оно же у
  isort и flake8.
- Целевая версия синтаксиса — **py311** (`target-version`), хотя Docker и CI крутятся на
  3.13. Форматтер не использует синтаксические возможности новее 3.11.
- Проверка в gate — `black --check` (только проверка, без записи). Чтобы реально
  отформатировать, запускайте `black` вручную **вне** gate — но фиксируйте результат, gate
  лишь проверяет.

---

## 2. Сортировка импортов — isort

Конфиг: `pyproject.toml:59-64`.

```toml
[tool.isort]
profile = "black"          # совместимость со стилем black (висячие запятые, скобки)
multi_line_output = 3       # вертикальная развёртка в скобках
line_length = 120           # совпадает с black/flake8
known_first_party = ["app"]
sections = ["FUTURE", "STDLIB", "THIRDPARTY", "FIRSTPARTY", "LOCALFOLDER"]
```

- `profile = "black"` обязателен — без него isort и black конфликтуют по стилю переносов.
- `known_first_party = ["app"]` — всё, что из пакета `app`, попадает в секцию `FIRSTPARTY`
  и идёт отдельным блоком после сторонних библиотек.
- Порядок секций фиксирован: будущие импорты → stdlib → сторонние → `app` → локальные.

---

## 3. Линтинг — Flake8 (+ bugbear)

Конфиг: `pyproject.toml:69-84` (читается через `flake8-pyproject`, иначе flake8 не видит
`pyproject.toml`).

```toml
[tool.flake8]
max-line-length = 120
extend-ignore = ["E203", "W503"]
exclude = [".git", "__pycache__", ".venv", "venv", "build", "dist", "*.egg-info"]
per-file-ignores = [
    "__init__.py:F401",
    "*/router.py:B008",
]
```

| Настройка | Значение | Зачем |
|---|---|---|
| `max-line-length` | 120 | согласовано с black/isort |
| `extend-ignore` E203 | пробел перед `:` | black ставит его в срезах — конфликт с flake8 |
| `extend-ignore` W503 | перенос перед бинарным оператором | стиль black; PEP 8 уже переобулся на W504 |
| `__init__.py:F401` | разрешить «неиспользуемые» импорты | паттерн ре-экспорта в `__init__.py` |
| `*/router.py:B008` | разрешить вызов в дефолте аргумента | FastAPI `Depends(...)` в дефолтах — это норма, а bugbear B008 их ругает |

**flake8-bugbear** (`flake8-bugbear`, `pyproject.toml:23`) добавляет серию проверок `B###`
(мутабельные дефолты, `except` без переменной и т.д.). Именно из-за неё нужен per-file-ignore
`B008` для роутеров FastAPI.

---

## 4. Типизация — MyPy

Конфиг: `pyproject.toml:89-104`. Профиль строгий, но не `strict = true` — флаги выставлены
поимённо:

```toml
[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_incomplete_defs = true
check_untyped_defs = true
disallow_untyped_decorators = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_no_return = true
warn_unreachable = true
strict_equality = true
show_error_codes = true
disable_error_code = ["no-untyped-def", "import-untyped"]
explicit_package_bases = true  # FIXME: Fix bug
```

| Флаг | Эффект |
|---|---|
| `warn_return_any` | ругается, если функция с типизированным возвратом отдаёт `Any` |
| `disallow_incomplete_defs` | нельзя частично типизировать сигнатуру (часть аргументов без типов) |
| `check_untyped_defs` | проверяет тела даже у нетипизированных функций |
| `disallow_untyped_decorators` | декоратор должен быть типизирован |
| `no_implicit_optional` | `def f(x: int = None)` запрещён — пишите `Optional[int]` / `int \| None` |
| `warn_redundant_casts` / `warn_unused_ignores` | ловит лишние `cast()` и неиспользуемые `# type: ignore` |
| `warn_no_return` / `warn_unreachable` | ветки без `return` и недостижимый код |
| `strict_equality` | запрещает сравнения заведомо несовместимых типов |
| `show_error_codes` | выводит код ошибки — пиши узкий `# type: ignore[code]`, а не голый |

Ослабления (важно понимать границы строгости):

- `disable_error_code = ["no-untyped-def", "import-untyped"]` — **не требуется** аннотировать
  каждую функцию полностью (хотя начатую сигнатуру надо доводить — см. `disallow_incomplete_defs`),
  и не падаем на сторонних пакетах без stubs.
- `explicit_package_bases = true` помечен `# FIXME` — это обход бага раскладки пакетов, а не
  осознанная конвенция. Не опирайтесь на него как на «фичу».
- Цель — `mypy app` (только пакет `app`, без `tests`; см. `scripts/gate.py:61`).

Примеры из кода, опирающиеся на этот профиль: явные `cast()` в `app/modules/rezka/_base.py:23,28`,
`@overload` для `get`/`post` (`_base.py:50-66`), узкие union-аннотации
`int | None` / `str | None` в `app/modules/rezka/service.py`.

---

## 5. Безопасность — Bandit

Конфиг: `pyproject.toml:158-161`. В gate запускается с `-c pyproject.toml`
(`scripts/gate.py:62`).

```toml
[tool.bandit]
exclude_dirs = ["tests", "test", "docs"]
skips = ["B101", "B104"]
```

| Skip | Что отключено | Почему оправдано |
|---|---|---|
| `B101` | `assert_used` | assert'ы в коде/тестах допустимы; их «удаление в `-O`» нам не критично |
| `B104` | `hardcoded_bind_all_interfaces` | сервис намеренно слушает `0.0.0.0` (контейнер/uvicorn `--host 0.0.0.0`) |

- Комментарий в конфиге прямо просит держать **только разумные skip'ы**, не весь список —
  не добавляйте новые без причины (`pyproject.toml:160`).
- Точечные подавления делаются **инлайн** через `# nosec <код>`, не глобально. Пример:
  `random.choice` для выбора прокси помечен `# nosec B311` в `app/modules/rezka/_base.py:23`
  (псевдослучайность не криптографическая — это ОК для ротации прокси).
- `exclude_dirs` убирает из скана `tests/`, `test/`, `docs/`.

---

## 6. Тесты — Pytest (+ coverage-ратчет)

Конфиг: `pyproject.toml:109-126`.

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = ["--verbose", "--color=yes", "--strict-markers", "--strict-config", "--rootdir=."]
filterwarnings = ["error", "ignore::DeprecationWarning"]
markers = ["asyncio: mark test as asyncio", "slow: mark test as slow"]
```

- `--strict-markers` + `--strict-config` — неизвестный маркер или опечатка в конфиге = ошибка.
  Любой новый маркер регистрируйте в `markers`.
- `filterwarnings = ["error", ...]` — **предупреждения = провал теста** (кроме
  `DeprecationWarning`). Не оставляйте warning'и в коде, который покрыт тестами.
- `asyncio_mode = "auto"` НЕ включён: на каждый async-тест **явно** ставится
  `@pytest.mark.asyncio` (см. `Sync-Mate-API-WS/CLAUDE.md:65`).
- `tests/conftest.py` автоматически чистит глобальный `RoomService._storage` между тестами —
  комнаты in-memory, иначе тесты потекут друг в друга.
- Mock httpx делается через `mocker.patch.object(service, "post"|"get", AsyncMock(...))`;
  WS-тесты используют `SimpleNamespace` + `mocker.AsyncMock()` для `add_user`/`remove_user`.

### Coverage-ратчет (strict)

`scripts/coverage_gate.py` читает `coverage.json` и сравнивает `totals.percent_covered`
с порогом `FLOOR = 85.0` (`scripts/coverage_gate.py:24`). Текущее покрытие ~88%.

- Порог — **храповик**: поднимать по мере роста покрытия, **никогда** не опускать без
  явной причины.
- Конфиг покрытия — `pyproject.toml:131-153`: источник `app`, исключаются тесты/`version.py`/
  `setup.py` и шаблонные строки (`def __repr__`, `if settings.DEBUG`, `raise NotImplementedError`
  и т.п.).

---

## 7. Направление слоёв (layer direction)

Проверяет `arch_lint_api.py::check_layers` (`scripts/arch_lint_api.py:62-76`).

Слои (сверху вниз):

```
main.py → api/router.py (REST) & ws/router.py (WS)
        → modules/room (handler · models · service) & modules/rezka
        → config
```

Правила:

1. Всё под `app/modules/**` **не имеет права** импортировать `app.api`, `app.ws`, `app.main`
   (нижний слой не знает о верхнем).
2. Сиблинг-изоляция модулей: `app/modules/rezka/*` не импортирует `app.modules.room`, и
   наоборот `app/modules/room/*` не импортирует `app.modules.rezka`. Модули не связаны
   напрямую — они общаются только через верхние слои.

Нарушение → `arch_lint_api.py` печатает `layer violation` / `cross-module coupling` и gate
падает (`scripts/arch_lint_api.py:69,73,76`).

---

## 8. Паритет `_VALID_ACTIONS` ↔ обработчик

Это защита от **исторического бага «действие молча принято, но без эффекта»**.

`UserHandler._VALID_ACTIONS` — это белый список входящих WS-действий
(`app/modules/room/handler.py:10`):

```python
_VALID_ACTIONS = frozenset({"play", "pause", "status", "load", "set_video", "info"})
```

### Что происходит шаг за шагом в `handle()` (`handler.py:20-46`)

1. `action = data.get("type")`.
2. Если `action not in self._VALID_ACTIONS` → `return` (молча отбрасываем неизвестное).
3. `info` → пишет произвольные метаданные в `user.info` и выходит (`handler.py:27-29`).
4. `set_video` → `_handle_set_video(data)` и выход (`handler.py:31-33`).
5. Иначе обновляет `user.current_time` / `user.downloaded_time` (`handler.py:35-36`).
6. Диспетчеризация по `if/elif`: `status` → `_handle_status`, `play` → `_handle_play`,
   `pause` → `_handle_pause`, `load` → `_handle_load` (`handler.py:38-45`).

**Ловушка:** если добавить строку в `_VALID_ACTIONS`, но забыть ветку в `if/elif` (и не
быть `info`/`set_video`), действие пройдёт фильтр на шаге 2, обновит тайминги на шаге 5 и
**молча провалится** мимо всех веток — клиент думает, что команда принята, а эффекта нет.

### Как это ловит линтер

`arch_lint_api.py::check_action_parity` (`scripts/arch_lint_api.py:79-97`) парсит
`_VALID_ACTIONS` и для каждого действия требует **либо** метод `def _handle_<action>`,
**либо** инлайн-ветку `action == "<action>"`. Нет ни того, ни другого → нарушение с прямым
текстом «it would be silently accepted with no effect». То есть `info` проходит как инлайн
(`action == "info"`), остальные — как `_handle_*`.

**Правило:** любая правка `_VALID_ACTIONS` обязана идти вместе с реализацией обработчика. И
поскольку `type` — часть WS-контракта, та же правка должна быть отражена на фронте — см. §11.

---

## 9. Только async HTTP (`httpx.AsyncClient`)

Проверяет `arch_lint_api.py::check_no_sync_http` (`scripts/arch_lint_api.py:100-107`).

Запрещено где-либо под `app/`:

- `import requests` / `from requests ...` — синхронная библиотека;
- `httpx.Client(...)` — синхронный клиент httpx.

Разрешён только `httpx.AsyncClient`. Эталон — `app/modules/rezka/_base.py:41`:

```python
async with httpx.AsyncClient(proxy=proxy, timeout=_DEFAULT_TIMEOUT, follow_redirects=True) as client:
    response = await client.request(method, self.URL.join(url), params=params, data=data)
    response.raise_for_status()
```

Следствия-конвенции:

- Все методы `RezkaService` / `RezkaStream` — **async** (`app/modules/rezka/service.py`).
  Из роутеров вызывайте через `await service.method(...)`.
- HTTP-ошибки rezka.ag (`httpx.HTTPError`) логируются и **пробрасываются**
  (`app/modules/rezka/_base.py:45-47`) → FastAPI отдаёт 500. Не глушите без причины.

---

## 10. Правила `asyncio.Lock`

`Room._lock: asyncio.Lock` (`app/modules/room/models.py:43`) сериализует доступ к общему
состоянию комнаты при конкурентных WS-соединениях.

### Под локом обязаны выполняться (и уже выполняются)

| Метод | Где | Что защищает |
|---|---|---|
| `add_user` | `models.py:45-47` | добавление в `user_storage` |
| `remove_user` | `models.py:49-52` | идемпотентное удаление (проверка `if user in ...`) |
| `check_is_loaded` | `models.py:67-83` | вычитка `user_storage` + рассылка `seek` отстающим + проверка готовности |

### Чего НЕЛЬЗЯ делать

**Не вызывайте** `room.play()` / `room.seek()` / `room.pause()` / `room.set_video_broadcast()`
**изнутри** блока `async with self._lock:`. Эти методы делают `await ... send_json(...)`
(рассылку), и пока корутина «висит» на отправке, параллельный `_handle_*` другого
пользователя попытается взять тот же лок → дедлок/рекурсивная блокировка. Если рассылка
нужна — выходите из лока, затем рассылайте.

Именно поэтому `check_is_loaded` сначала под локом вычисляет готовность и шлёт только
корректирующие `seek` отстающим, а собственно `play()` / `remove_block_pause()` вызываются
**снаружи**, из обработчиков (`handler.py:50-54`, `66-67`, `82-86`).

### Идемпотентность удаления

Не пишите `room.user_storage.remove(user)` напрямую — это и не под локом, и кинет
`ValueError`, если пользователя уже нет. Используйте только `await room.remove_user(user)`
(`models.py:49-52`) — он под локом и идемпотентен.

---

## 11. WS: `await room.remove_user(user)` в `finally`

В WS-роутере (`app/ws/router.py:16-55`) жизненный цикл соединения такой:

1. `accept()`, поиск комнаты; нет комнаты → close `4000` (`router.py:24-27`).
2. Первое сообщение **обязано** быть `{"type":"connect","name":"..."}` и валидируется
   `ConnectMessage` (`app/ws/schemas.py`, `type: Literal["connect"]`); иначе close `4001`
   (`router.py:29-34`).
3. `User(...)` → `await room.add_user(user)` → ответ `{"type":"connect","id":<uuid>}`
   (`router.py:36-39`).
4. Основной цикл: `receive_json()` → `handler.handle(data)` (`router.py:42-44`).
5. **`finally: await room.remove_user(user)`** (`router.py:54-55`).

**Правило:** строку `await room.remove_user(user)` из `finally` убирать нельзя — иначе при
любом разрыве (`WebSocketDisconnect`, исключение, серверная ошибка `1011`) пользователь
останется в `user_storage` навсегда. Это утечка: «мёртвый» пользователь будет вечно числиться
неготовым и **заблокирует запуск воспроизведения** для всей комнаты (см. логику `check_is_loaded`,
`models.py:77-80`) и помешает удалить комнату (`RoomService.delete_room` отказывает, пока
`user_storage` непуст — `service.py:29-34`).

---

## 12. WS-протокол — кросс-проектный инвариант

Множество строк `type` WebSocket-сообщений — **контракт, общий для бэка и фронта**. Любая
правка `type` на одной стороне обязана быть зеркально отражена на другой, иначе синхронизация
ломается молча.

Проверяет `scripts/protocol_sync.py` (gate-проверка `protocol`, запускается в **обоих**
gate'ах). Он собирает бэкенд-множество типов из:

- `_VALID_ACTIONS` в `handler.py` (входящие, `protocol_sync.py:71-74`);
- `Literal["..."]` в `app/ws/schemas.py` (handshake, `protocol_sync.py:77-78`);
- всех `{"type": "..."}` и `obj["type"] = "..."` по `app/**.py` (исходящие,
  `protocol_sync.py:82-85`);

и сравнивает с `enum WSMessageTypes` фронта. Дрейф → exit 1 с указанием, какой стороне какого
типа не хватает. Текущий набор (9 типов): `connect · info · play · pause · seek · status ·
load · set_video · remove_block_pause`.

> Не путайте `WSMessageTypes` (протокол с сервером) и `BrowserMessageTypes` (внутренний IPC
> расширения) — это разные enum'ы на фронте.

После правки протокола обновляйте `docs/websocket-protocol.md` и прогоняйте gate на обеих сторонах.

---

## 13. Конфигурация и переменные окружения

`Settings` (`app/config.py`) читает `.env` через pydantic-settings (`extra="ignore"`).
**Имена** переменных (значения — в `.env`, его не читать и не коммитить):

| Имя | Назначение |
|---|---|
| `REQUIRED_DOWNLOAD_TIME` | сколько секунд буфера нужно у каждого, чтобы комната считалась «загруженной» |
| `REZKA_URL` | базовый URL rezka.ag |
| `PROXIES_LIST` | CSV-строка прокси; `Settings.__init__` сам распарсит её в список (`config.py:25-28`) |
| `debug` | флаг отладки |

Деплой/инфра-секреты (имена; живут в GitHub Secrets и/или локальном `.env`):
`CLOUDFLARE_TUNNEL_TOKEN`, `SERVER_PORT`, `SERVER_HOST`, `SSH_PRIVATE_KEY`, `PROXIES_LIST`.

`.env` — **off-limits**: содержит реальный `CLOUDFLARE_TUNNEL_TOKEN`. Не читать, не
редактировать, не коммитить (deny-list в `.claude/settings.json`).

---

## 14. CI и деплой — актуальное состояние (не верьте старому DOCUMENTATION.md)

Старый корневой `DOCUMENTATION.md` частично устарел по части деплоя. Реальность по конфигам:

- **Docker Compose — один сервис.** `docker-compose.yml:1-8` содержит **только**
  `sync-mate-api-ws` (build + image + ports). Сервис `cloudflared` был **удалён** (коммит
  `f0c7443`). Туннель Cloudflare теперь поднимается отдельно (см. цели `tunnel` / `run` в
  `Makefile:23-36`), а не как контейнер compose.
- **CI тестирует только на Python 3.13.** Все джобы в `.github/workflows/ci.yml`
  (`lint-format`, `type-check`, `security`, `test`) используют `python-version: '3.13'`
  (`ci.yml:19,57,90,130`) — матрицы `3.11/3.12/3.13` **нет**. При этом black таргетит `py311`,
  а mypy — `python_version = "3.11"`: язык кода ограничен 3.11, а прогон идёт на 3.13.
- CI запускает инструменты **напрямую** (`black --check`, `flake8`, `mypy`, `bandit`,
  `pytest --cov`), не через gate. Локально же — только gate. При изменении набора проверок
  синхронизируйте `scripts/gate.py` и `.github/workflows/ci.yml`.
- В CI всё ещё присутствует шаг `safety check` (`ci.yml:114-116`) — в **gate** его нет
  намеренно (см. §0).

---

## 15. Полный список «Что НЕ делать» (с обоснованием)

### Бэкенд-специфичное

| Не делать | Почему |
|---|---|
| Не возвращать sync `httpx` (`requests`, `httpx.Client`) | проект async-only; ловит `arch_lint_api.py::check_no_sync_http` (§9). Sync-вызов заблокирует event loop |
| Не добавлять действие в `_VALID_ACTIONS` без `_handle_*`/инлайн-ветки | иначе «молча принято без эффекта» — исторический баг; ловит `check_action_parity` (§8) |
| Не убирать `await room.remove_user(user)` из `finally` в `ws/router.py` | утечка пользователя → вечная блокировка запуска комнаты и невозможность её удалить (§11) |
| Не писать `room.user_storage.remove(user)` напрямую | не под локом и кинет `ValueError`; нужен идемпотентный `await room.remove_user(user)` (§10) |
| Не вызывать `play()`/`seek()`/`pause()`/`set_video_broadcast()` внутри `async with self._lock` | рекурсивная блокировка/дедлок на параллельном `_handle_*` (§10) |
| Не глушить `httpx.HTTPError` из rezka без причины | ошибки rezka.ag должны доходить до клиента как 500 (`_base.py:45-47`) |
| Не нарушать направление слоёв | `modules/**` не импортирует `api`/`ws`/`main`; `rezka` ⊥ `room` (§7) |
| Не менять `type` WS-сообщения только на бэке | сломает синхронизацию; правьте обе стороны + `docs/websocket-protocol.md`, ловит `protocol_sync.py` (§12) |

### Инструменты и процесс

| Не делать | Почему |
|---|---|
| Не вызывать `pytest`/`mypy`/`black`/`isort`/`flake8`/`bandit` вручную в сессии | единственный санкционированный вход — `python scripts/gate.py --repo api` (§0) |
| Не добавлять `safety` в gate | задепрекейчен, нужна лицензия, падает headless; CVE-скан остаётся в CI/`pip-audit` (§0) |
| Не опускать `FLOOR` в `coverage_gate.py` без явной причины | порог покрытия — храповик, только вверх (§6) |
| Не плодить новые `skips` в `[tool.bandit]` | держим «только разумные» B101/B104; точечно — инлайн `# nosec` (§5) |
| Не убирать `profile = "black"` из isort / не менять `line-length`/`max-line-length` с 120 | рассинхрон black ⇄ isort ⇄ flake8 (§1–§3) |
| Не регистрировать тесты без явного `@pytest.mark.asyncio` для async | `asyncio_mode` не `auto`; `--strict-markers` (§6) |

### Общепроектное (из корневого `CLAUDE.md`)

| Не делать | Почему |
|---|---|
| Не пушить без явного запроса | push = запуск CI; делает пользователь вручную / через `/push` |
| Не коммитить без явного запроса; коммит — одна короткая строка в повелительном наклонении | стиль фиксирован; **никаких** `Co-Authored-By`/`Generated with`/эмодзи — это блокирует `guard-git` |
| Никогда `--no-verify` / `--no-gpg-sign`, никаких force-push / `reset --hard origin` | блокируется `guard-git`; ломает историю |
| Не добавлять YouTube | сознательное ограничение, не «забытый кусок»; отдельная фича (`YouTubeLocators` + `pickLocators` + `wxt.config.ts`) |
| Не переходить на Redis/Postgres | in-memory `RoomService._storage` согласован; персистентности нет намеренно |
| Не реализовывать автоудаление пустых комнат | удаление только вручную через REST `DELETE`; это by design |
| Не читать/не редактировать/не коммитить `.env` | реальный `CLOUDFLARE_TUNNEL_TOKEN`; off-limits (§13) |

---

## См. также

- [`../CLAUDE.md`](../CLAUDE.md) — тонкие канонические правила бэкенда (стек, запуск, race conditions).
- [`../../CLAUDE.md`](../../CLAUDE.md) — корневой гид по обоим подпроектам.
- [`../../DOCUMENTATION.md`](../../DOCUMENTATION.md) — полная техдокументация и WS-протокол (docs/websocket-protocol.md)
  (учтите дрейф по деплою — см. §14).
- [`../../.claude/docs/architecture.md`](../../.claude/docs/architecture.md) — слои и инварианты,
  которые проверяют arch/protocol-чеки.
- [`../../.claude/docs/conventions.md`](../../.claude/docs/conventions.md) — конвенции уровня
  всего воркспейса (коммиты, gate, версии/теги, `.env`).
- [`../../.claude/docs/workflow.md`](../../.claude/docs/workflow.md) и
  [`../../.claude/docs/faq.md`](../../.claude/docs/faq.md) — жизненный цикл задачи и «меня
  заблокировал гард».
- [`../../scripts/README.md`](../../scripts/README.md) — обзор `gate.py`, `arch_lint_api.py`,
  `protocol_sync.py`, `coverage_gate.py`.
