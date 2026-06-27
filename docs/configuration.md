# Конфигурация и запуск (Sync-Mate-API-WS)

Полный справочник по конфигурации бэкенда: класс `Settings`, загрузка `.env`, все переменные окружения, локальный запуск через Poetry, цели `Makefile`, Docker/Compose и CI/CD.

---

## 1. Где живёт конфигурация

| Слой | Файл | Что делает |
|---|---|---|
| Прикладные настройки | `app/config.py` | Класс `Settings` (Pydantic) + singleton `settings` |
| Файл значений | `.env` (в корне `Sync-Mate-API-WS/`) | Реальные значения переменных окружения. **В `.gitignore`, но физически присутствует** (см. §9) |
| Локальный запуск + туннель | `Makefile` | Цели `up/down/logs/dev/tunnel/tunnel-quick/run` |
| Контейнер | `Dockerfile`, `docker-compose.yml` | Сборка образа и единственный сервис |
| Конвейеры | `.github/workflows/ci.yml`, `.github/workflows/cd.yml` | Линт/типы/тесты и сборка-деплой образа |

Единственный источник прикладной конфигурации в рантайме — объект `settings` из `app/config.py`. Всё остальное (`Makefile`, `docker-compose.yml`) использует переменные окружения напрямую, минуя Pydantic.

---

## 2. Класс `Settings` (`app/config.py`)

`app/config.py` целиком (≈31 строка):

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Sync-Mate-API-WS"
    description: str = (
        "SyncMate API WS is a REST and WebSocket service "
        "providing synchronized video playback control, "
        "metadata streams, and video sources retrieval "
        "from YouTube and Rezka.ag."
    )
    author: str = "Zebaro (zebaro.dev)"
    version: str = "0.1.1"

    debug: bool = False

    REQUIRED_DOWNLOAD_TIME: int = 15

    REZKA_URL: str = "https://rezka.ag"

    PROXIES_LIST: list | str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if isinstance(self.PROXIES_LIST, str):
            self.PROXIES_LIST = [p.strip() for p in self.PROXIES_LIST.split(",")]


settings = Settings()
```

`Settings` наследуется от `pydantic_settings.BaseSettings` (`app/config.py:4`), поэтому каждое поле может быть переопределено одноимённой переменной окружения (по умолчанию **регистронезависимо**, см. §4).

### 2.1. Поля и их значение

| Поле (`config.py:line`) | Тип | Дефолт | Назначение | Где читается |
|---|---|---|---|---|
| `app_name` (`:5`) | `str` | `"Sync-Mate-API-WS"` | Имя приложения (метаданные) | `main.py:47` (`title=`), `api/router.py:16` |
| `description` (`:6`) | `str` | длинная строка (см. выше) | Описание API в OpenAPI | `main.py:48`, `api/router.py:17` |
| `author` (`:12`) | `str` | `"Zebaro (zebaro.dev)"` | Автор (метаданные) | `api/router.py:18` |
| `version` (`:13`) | `str` | `"0.1.1"` | Версия API в OpenAPI/корневом ответе | `main.py:49`, `api/router.py:19` |
| `debug` (`:15`) | `bool` | `False` | Режим отладки FastAPI + уровень логов | `main.py:28`, `main.py:50` |
| `REQUIRED_DOWNLOAD_TIME` (`:17`) | `int` | `15` | Порог буферизации (сек) для старта синхронного воспроизведения | `modules/room/models.py:78` |
| `REZKA_URL` (`:19`) | `str` | `"https://rezka.ag"` | Базовый URL Rezka для всех HTTP-запросов | `modules/rezka/_base.py:17` |
| `PROXIES_LIST` (`:21`) | `list \| str \| None` | `None` | Список HTTP-прокси для запросов к Rezka | `modules/rezka/_base.py:18` |

> Поля-метаданные (`app_name`, `description`, `author`, `version`) технически тоже переопределяемы через окружение (`APP_NAME`, `DESCRIPTION`, …), но менять их так не предполагается — это просто значения по умолчанию для OpenAPI и корневого REST-ответа.

### 2.2. `debug`

- Тип `bool`, дефолт `False` (`config.py:15`).
- Управляется переменной окружения `DEBUG` (имя поля в нижнем регистре, но матчинг регистронезависимый).
- Эффекты в `app/main.py`:
  - Уровень логгера `app`: `"DEBUG" if settings.debug else "INFO"` (`main.py:28`).
  - Прокидывается в `FastAPI(debug=settings.debug)` (`main.py:50`) — включает подробные traceback'и.
- Pydantic парсит булевы значения из строк (`true/false`, `1/0`, `yes/no`, `on/off`).

### 2.3. `REQUIRED_DOWNLOAD_TIME`

- Тип `int`, дефолт `15` (секунд) (`config.py:17`).
- **Смысл:** минимальный объём предзагруженного («забуференного») видео, который должен быть у *каждого* участника комнаты, прежде чем сервер разрешит синхронный старт.
- Используется в `Room.check_is_loaded` (`modules/room/models.py:77-80`):

```python
all_ready = len(self.user_storage) > 0 and all(
    u.current_time == self.current_time and u.downloaded_time >= settings.REQUIRED_DOWNLOAD_TIME
    for u in self.user_storage
)
```

  То есть комната считается «готовой» (`is_loaded = True`), только когда у всех пользователей текущая позиция совпадает с комнатной **и** `downloaded_time >= REQUIRED_DOWNLOAD_TIME`. Уменьшение значения ускоряет старт, но повышает риск рассинхрона на медленном интернете; увеличение делает старт более «уверенным», но более долгим.

### 2.4. `REZKA_URL`

- Тип `str`, дефолт `"https://rezka.ag"` (`config.py:19`).
- **Смысл:** базовый адрес зеркала Rezka. Все запросы строятся относительно него.
- Используется в `RezkaBase` как класс-атрибут (`modules/rezka/_base.py:17`):

```python
class RezkaBase:
    URL = httpx.URL(settings.REZKA_URL)
    PROXIES_LIST = settings.PROXIES_LIST
```

  Конкретные URL получаются через `self.URL.join(url)` (`_base.py:43`). Если Rezka переедет на другой домен/зеркало — меняется только `REZKA_URL` в окружении, код трогать не нужно.
- **Гоча:** `URL` и `PROXIES_LIST` в `RezkaBase` — атрибуты *класса*, вычисляемые один раз в момент импорта `_base.py`. Поскольку singleton `settings` создаётся ещё раньше (при импорте `app.config`), к этому моменту значения уже финализированы. Менять `REZKA_URL` в рантайме после старта процесса бесполезно — нужен перезапуск.

### 2.5. `PROXIES_LIST` (и кастомный `__init__`)

- Тип-объединение `list | str | None`, дефолт `None` (`config.py:21`).
- **Смысл:** пул HTTP(S)-прокси, из которого на *каждый* запрос к Rezka выбирается случайный (`modules/rezka/_base.py:20-23`):

```python
def _get_random_proxy(self) -> str | None:
    if not self.PROXIES_LIST:
        return None
    return cast(str, choice(self.PROXIES_LIST))  # nosec B311
```

  Выбранный прокси передаётся в `httpx.AsyncClient(proxy=proxy, ...)` (`_base.py:41`). Если список пуст/`None` — запросы идут напрямую.

#### Кастомный `__init__` — CSV-разбор шаг за шагом (`config.py:25-28`)

```python
def __init__(self, **kwargs):
    super().__init__(**kwargs)
    if isinstance(self.PROXIES_LIST, str):
        self.PROXIES_LIST = [p.strip() for p in self.PROXIES_LIST.split(",")]
```

Что происходит:

1. `super().__init__(**kwargs)` — обычная инициализация Pydantic: читаются `.env` и окружение.
2. Тип поля — объединение, включающее `str`, поэтому Pydantic принимает «сырую» строку из окружения как есть (CSV вида `http://a:8080,http://b:8080` не является валидным JSON-списком, и именно наличие `str` в union позволяет Pydantic положить её в поле строкой, не падая).
3. Если в итоге в `PROXIES_LIST` оказалась строка — она разбивается по запятой, каждый элемент очищается `.strip()`, и поле становится `list[str]`.
4. Если значение не задано (`None`) — остаётся `None`, разбор пропускается.

Таким образом в окружении прокси задаются **одной CSV-строкой**, а в коде вы всегда работаете со списком (либо `None`).

**Гочи:**
- Пустая строка `PROXIES_LIST=` превратится в `[""]` (список из одного пустого элемента), а не в `[]`. Тогда `not self.PROXIES_LIST` ложно, и `_get_random_proxy` вернёт `""` (пустой прокси), что приведёт к неожиданному поведению `httpx`. Если прокси не нужны — **не задавайте переменную вовсе** (оставьте `None`), а не пустую строку.
- В CI значение приходит из секрета: `PROXIES_LIST: ${{ secrets.PROXIES_LIST }}` (`ci.yml:123`) для джоба тестов.

### 2.6. Singleton `settings`

`settings = Settings()` (`config.py:31`) — единственный экземпляр, создаётся при первом импорте модуля `app.config`. Все потребители импортируют именно его: `from app.config import settings` (`main.py:7`, `api/router.py:3`, `modules/room/models.py:8`, `modules/rezka/_base.py:8`). Отдельных «контекстов конфигурации» нет — конфигурация глобальна и иммутабельна на время жизни процесса.

---

## 3. `model_config` и загрузка `.env`

```python
model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
```

(`config.py:23`)

| Параметр | Значение | Эффект |
|---|---|---|
| `env_file` | `".env"` | Pydantic читает файл `.env` из **текущей рабочей директории** процесса |
| `env_file_encoding` | `"utf-8"` | Кодировка файла |
| `extra` | `"ignore"` | Неизвестные переменные в `.env`/окружении **игнорируются**, а не вызывают ошибку |

`extra="ignore"` — ключевой момент: в `.env` лежат и переменные, которые `Settings` не объявляет (например `SERVER_PORT`, `CLOUDFLARE_TUNNEL_TOKEN` — их читают Compose и `Makefile`, а не Pydantic). Без `extra="ignore"` Pydantic упал бы на них с `ValidationError`.

### Путь к `.env` — важная тонкость

`env_file=".env"` — **относительный путь**. Pydantic ищет его относительно директории, из которой запущен процесс (CWD), а не относительно `config.py`. Поэтому uvicorn/poetry нужно запускать из корня `Sync-Mate-API-WS/`. В Docker рабочая директория `/app` (`Dockerfile:2`, `WORKDIR /app`), куда `.env` копируется вместе со всем кодом (`COPY . /app`, `Dockerfile:11`) — но в контейнере значения обычно приходят через окружение, а не через файл.

### Порядок приоритетов (Pydantic Settings)

От высшего к низшему:

1. Аргументы конструктора `Settings(**kwargs)` (в проекте не используются).
2. **Переменные окружения процесса** (реальные `export`/`env`).
3. Значения из **`.env`**.
4. Дефолты, заданные в классе.

Из этого следует: реальная переменная окружения перекрывает то же значение из `.env`. Например, `export DEBUG=true` переопределит `DEBUG` из файла.

---

## 4. Переменные окружения (только имена)

> Ниже перечислены **только имена** переменных. Содержимое `.env` не приводится и не должно читаться (см. §9).

### 4.1. Читаются классом `Settings` (Pydantic)

Матчинг регистронезависимый (дефолт `BaseSettings`), поэтому переменные принято писать в верхнем регистре.

| Имя переменной | Соответствует полю | Тип | Дефолт |
|---|---|---|---|
| `DEBUG` | `debug` | bool | `False` |
| `REQUIRED_DOWNLOAD_TIME` | `REQUIRED_DOWNLOAD_TIME` | int | `15` |
| `REZKA_URL` | `REZKA_URL` | str | `https://rezka.ag` |
| `PROXIES_LIST` | `PROXIES_LIST` | CSV-строка → `list` | `None` |

(Технически также `APP_NAME`, `DESCRIPTION`, `AUTHOR`, `VERSION` — но переопределять их не предполагается.)

### 4.2. Читаются инфраструктурой (не Pydantic)

| Имя переменной | Кто читает | Назначение |
|---|---|---|
| `SERVER_PORT` | `docker-compose.yml:8` (`${SERVER_PORT:-8000}`), `cd.yml:87` | Внешний порт публикации контейнера (дефолт `8000`) |
| `CLOUDFLARE_TUNNEL_TOKEN` | `Makefile:24`, `Makefile:35` | Токен именованного туннеля Cloudflare для целей `tunnel`/`run` |
| `PORT` | `Makefile:4` (`PORT ?= 8000`) | Порт uvicorn для локальных целей `dev`/`tunnel-quick`/`run` (это Make-переменная, не из `.env`, если её там нет) |

`Makefile` в строках 1-2 делает `include .env` + `export`, то есть **все** переменные из `.env` экспортируются в окружение для дочерних команд (`docker compose`, `cloudflared`, `uvicorn`). Именно так `SERVER_PORT` и `CLOUDFLARE_TUNNEL_TOKEN` из `.env` попадают в Compose и туннель.

---

## 5. Локальный запуск (Poetry)

Требования: Python 3.11+ (`pyproject.toml:10`, `python = "^3.11"`), Poetry.

```bash
# из корня Sync-Mate-API-WS/
poetry install                                   # установить зависимости (включая dev)
poetry run uvicorn app.main:app --reload         # запуск с автоперезагрузкой
# → http://127.0.0.1:8000
```

Альтернатива из README — активировать окружение и звать uvicorn напрямую:

```bash
poetry shell
uvicorn app.main:app --reload
```

Приложение FastAPI собирается в `app/main.py` (`app = FastAPI(...)`, `main.py:46`), подключая роутеры `/api` (`main.py:61`) и `/ws` (`main.py:62`). CORS открыт для всех origin'ов (`main.py:53-59`).

### Тесты, линт, типы

```bash
poetry run pytest                                # тесты (testpaths=["tests"], pyproject.toml:110)
poetry run pytest --cov=app --cov-report=term-missing   # с покрытием (как в CI)

poetry run black --check app tests               # формат
poetry run isort --check-only app tests          # сортировка импортов
poetry run flake8 app tests                      # линт
poetry run mypy app                              # типы
poetry run bandit -r app                         # безопасность
```

Конфигурация всех инструментов — в `pyproject.toml` (black/isort/flake8/mypy line-length 120; pytest с `--strict-markers --strict-config` и `filterwarnings = ["error", ...]`).

---

## 6. `Makefile` — цели

`Makefile` начинается с `include .env` + `export` (`Makefile:1-2`) и `PORT ?= 8000` (`Makefile:4`).

| Цель | Команда | Что делает |
|---|---|---|
| `up` | `docker compose -p sync-mate up -d --build` (`:8-9`) | Собрать и поднять контейнер в фоне (проект `sync-mate`) |
| `down` | `docker compose -p sync-mate down` (`:11-12`) | Остановить и удалить контейнеры проекта |
| `logs` | `docker compose -p sync-mate logs -f` (`:14-15`) | Хвост логов контейнера |
| `dev` | `poetry run uvicorn app.main:app --host 0.0.0.0 --port $(PORT) --reload` (`:19-20`) | Локальный dev-сервер с автоперезагрузкой на `$(PORT)` |
| `tunnel` | `cloudflared tunnel --no-autoupdate run --token $(CLOUDFLARE_TUNNEL_TOKEN)` (`:23-24`) | Именованный Cloudflare-туннель (токен из `.env`) |
| `tunnel-quick` | `cloudflared tunnel --url http://localhost:$(PORT)` (`:27-28`) | Быстрый временный туннель `*.trycloudflare.com` (без токена) |
| `run` | uvicorn + cloudflared вместе (`:31-36`) | Запуск сервера и именованного туннеля одновременно; `Ctrl+C` гасит оба (`trap 'kill 0' INT`) |

Деталь по `run` (`Makefile:31-36`): запускает `uvicorn ... --host 0.0.0.0 --port $(PORT)` и `cloudflared ... --token $(CLOUDFLARE_TUNNEL_TOKEN)` в фоне (`&`), затем `wait`; ловушка `trap 'kill 0' INT` гарантирует, что прерывание (`Ctrl+C`) завершит обе фоновые задачи.

> `tunnel`/`run` требуют установленного `cloudflared` и непустого `CLOUDFLARE_TUNNEL_TOKEN` в `.env`. `up`/`down`/`logs` требуют Docker. `dev`/`tunnel-quick` достаточно Poetry/cloudflared.

---

## 7. Docker и `docker-compose.yml`

### Dockerfile

`Dockerfile` (`:1-16`): база `python:3.13-slim`, `WORKDIR /app`, установка Poetry, `poetry install --no-root --without dev` (без dev-зависимостей), копирование кода, `EXPOSE 8000`, запуск `uvicorn app.main:app --host 0.0.0.0 --port 8000`.

### docker-compose.yml — ОДИН сервис

```yaml
services:
  sync-mate-api-ws:
    build: .
    image: ghcr.io/zebaro24/sync-mate-api-ws:latest
    container_name: sync-mate-api-ws
    restart: unless-stopped
    ports:
      - "${SERVER_PORT:-8000}:8000"
```

(`docker-compose.yml:1-8`)

- **Сервис ровно один** — `sync-mate-api-ws`. Сервис `cloudflared` из Compose **удалён** (коммит `f0c7443` «Remove cloudflared from docker-compose»). Туннель теперь поднимается отдельно (через `Makefile`-цели `tunnel`/`run` локально, либо инфраструктурно на сервере), а не как часть Compose-стека.
- Публикация порта: `${SERVER_PORT:-8000}:8000` — внешний порт берётся из `SERVER_PORT`, иначе `8000`; внутри контейнера всегда `8000`.
- `restart: unless-stopped` — автоперезапуск контейнера.
- `image: ghcr.io/zebaro24/sync-mate-api-ws:latest` — образ из GHCR (его собирает CD).

> Историческая справка / дрейф документации: старый корневой `DOCUMENTATION.md` может описывать Compose с двумя сервисами (включая `cloudflared`). Это **устарело** — доверяйте текущему `docker-compose.yml`.

---

## 8. CI/CD

### CI (`.github/workflows/ci.yml`)

Триггеры: `push`/`pull_request` в `main`/`master` (`ci.yml:3-7`). Джобы:

| Джоб | Что делает | Python |
|---|---|---|
| `lint-format` | `black --check`, `isort --check-only`, `flake8` (`ci.yml:40-46`) | `3.13` (`:19`) |
| `type-check` | `mypy app` (`ci.yml:78-79`) | `3.13` (`:57`) |
| `security` | `bandit -r app`, `safety check` (`ci.yml:111-116`) | `3.13` (`:90`) |
| `test` | `pytest --cov=app --cov-report=xml --cov-report=term-missing` + upload в Codecov (`ci.yml:151-158`) | `3.13` (`:130`) |

- **Тесты гоняются только на Python 3.13** — матрицы версий (3.11/3.12/3.13) нет, несмотря на то что `pyproject.toml` объявляет совместимость с `^3.11`. Локально можно использовать 3.11+, но CI валидирует именно 3.13.
- Джоб `test` задаёт окружение `PYTHONPATH: .` и `PROXIES_LIST: ${{ secrets.PROXIES_LIST }}` (`ci.yml:121-123`).
- Poetry ставится через `abatilo/actions-poetry@v3` с `poetry-version: '1.8.0'`.

### CD (`.github/workflows/cd.yml`)

Триггер: пуш тега `v*` (`cd.yml:3-6`). Шаги:
1. `build-and-push` — собирает Docker-образ, тегирует версией из тега и `latest`, пушит в GHCR (`cd.yml:46-54`).
2. `deploy` — по SSH копирует `docker-compose.yml` на сервер, экспортирует `SERVER_PORT=${{ vars.SERVER_PORT }}` (`cd.yml:87`) и поднимает стек `docker compose -p sync-mate up -d --pull always` (`cd.yml:89`), затем `docker image prune -f`.

URL прод-окружения: `https://sync-mate-api-ws.zebaro.dev` (`cd.yml:61`).

---

## 9. Секреты и `.env`

- `.env` указан в `.gitignore` (`/.gitignore:139`, плюс `.envrc` на `:140`), **но физически присутствует** в рабочем дереве `Sync-Mate-API-WS/.env` и содержит **реальный секрет** — `CLOUDFLARE_TUNNEL_TOKEN` (а также `SERVER_PORT` и при необходимости `PROXIES_LIST`).
- **НЕ читать и не печатать содержимое `.env`.** Не редактировать без явной необходимости и не коммитить изменения файла.
- Прочие секреты живут в GitHub: `secrets.PROXIES_LIST` (CI), `secrets.GITHUB_TOKEN`, `secrets.SERVER_HOST`, `secrets.SERVER_USER`, `secrets.SSH_PRIVATE_KEY` и `vars.SERVER_PORT` (CD).

---

## 10. Гочи и краевые случаи (сводка)

- **CWD имеет значение.** `env_file=".env"` относителен рабочей директории — запускайте из корня `Sync-Mate-API-WS/`, иначе `.env` не подхватится (останутся дефолты).
- **`PROXIES_LIST=` (пустая строка)** даёт `[""]`, а не `[]`; это ломает выбор прокси. Не задавайте переменную вовсе, если прокси не нужны.
- **`extra="ignore"`** позволяет держать в `.env` инфраструктурные переменные (`SERVER_PORT`, `CLOUDFLARE_TUNNEL_TOKEN`), которые Pydantic не знает, — они не вызывают ошибок валидации.
- **Конфигурация иммутабельна в рантайме.** `RezkaBase.URL` / `RezkaBase.PROXIES_LIST` фиксируются при импорте; смена окружения после старта процесса требует перезапуска.
- **CI ≠ совместимость.** Объявлено `python = "^3.11"`, но CI/тесты идут только на 3.13.
- **Compose — один сервис.** `cloudflared` убран из Compose; туннель поднимается отдельно.

---

## См. также

- [`docs/`](.) — остальные справочники бэкенда (WS-протокол, модули `room`/`rezka`, REST-роутеры).
- [`../CLAUDE.md`](../CLAUDE.md) — гид Claude по бэкенд-части (раздел «Конфигурация»).
- [`../../CLAUDE.md`](../../CLAUDE.md) — общий гид по репозиторию Sync-Mate.
- [`../../DOCUMENTATION.md`](../../DOCUMENTATION.md) — полная техническая документация (учтите: раздел деплоя частично устарел — доверяйте коду/конфигам).
- [`../README.md`](../README.md) — краткое README бэкенда.
