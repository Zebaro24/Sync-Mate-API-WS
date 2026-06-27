# Деплой, сборка и CI/CD — Sync-Mate-API-WS

Исчерпывающий справочник по тому, как бэкенд собирается в Docker-образ, проверяется в CI и выкатывается в прод по тегу `v*`.

> [!IMPORTANT]
> Этот документ — источник истины по деплою. Корневой `../../DOCUMENTATION.md` в части деплоя **устарел** (он описывает старую схему с двумя сервисами docker-compose, включая `cloudflared`). В коммите `f0c7443` («Remove cloudflared from docker-compose») второй сервис был удалён — сейчас в `docker-compose.yml` **один** сервис. Доверяйте коду и конфигам в этом репозитории, а не старой документации.

---

## 1. Карта артефактов

| Файл | Назначение |
|---|---|
| `Dockerfile` | Сборка образа приложения (`python:3.13-slim` + uvicorn) |
| `docker-compose.yml` | Один сервис `sync-mate-api-ws`; используется и локально (`make up`), и на сервере |
| `.github/workflows/ci.yml` | CI: lint/format, типы, безопасность, тесты — на каждый push/PR в `main`/`master` |
| `.github/workflows/cd.yml` | CD: сборка → push в GHCR → деплой на сервер по SSH — **только по тегу `v*`** |
| `Makefile` | Локальные команды разработчика (docker, uvicorn, cloudflared-туннель) |
| `app/config.py` | `Settings` (Pydantic) — читает `.env`, поле `version` |
| `pyproject.toml` | Версия пакета и зависимости (Poetry) |

Реестр образов: **`ghcr.io/zebaro24/sync-mate-api-ws`** (GitHub Container Registry).
Прод-URL: **`https://sync-mate-api-ws.zebaro.dev`**.
Репозиторий: `github.com/Zebaro24/Sync-Mate-API-WS`.

---

## 2. Сборка образа (`Dockerfile`)

```dockerfile
FROM python:3.13-slim
WORKDIR /app

RUN pip install --upgrade pip && pip install poetry

COPY pyproject.toml poetry.lock* /app/

RUN poetry config virtualenvs.create false \
    && poetry install --no-root --without dev --no-interaction --no-ansi

COPY . /app

ENV PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Что происходит шаг за шагом (`Dockerfile:1`–`Dockerfile:16`):

1. **Базовый образ** — `python:3.13-slim` (`Dockerfile:1`). Версия Python здесь должна совпадать с CI (тоже 3.13, см. §4); расхождение базы и CI прятало бы баги до момента деплоя.
2. **Poetry ставится глобально** через `pip install poetry` (`Dockerfile:4`). В отличие от CI, версия Poetry **не закреплена** — берётся последняя из PyPI. В CI же зафиксирована `1.8.0` (`ci.yml:35`). Это потенциальный источник расхождений при сборке.
3. **Сначала копируются только манифесты** `pyproject.toml` и `poetry.lock*` (`Dockerfile:6`) — звёздочка делает lock-файл опциональным. Это сделано ради кеша слоёв Docker: пока зависимости не менялись, слой установки переиспользуется.
4. **`virtualenvs.create false`** (`Dockerfile:8`) — Poetry ставит пакеты прямо в системный Python образа, без venv (внутри контейнера он не нужен).
5. **`poetry install --no-root --without dev`** (`Dockerfile:9`):
   - `--no-root` — сам проект как пакет не ставится (в `pyproject.toml` указано `package-mode = false`), ставятся только зависимости.
   - `--without dev` — dev-группа (black, isort, flake8, mypy, pytest, bandit, safety и т. д.) в прод-образ **не попадает**. Образ тоньше и без инструментов разработки.
   - `--no-interaction --no-ansi` — неинтерактивный режим для CI/сборки.
6. **Копируется весь исходник** `COPY . /app` (`Dockerfile:11`) — отдельным слоем после установки зависимостей.
7. **`PYTHONUNBUFFERED=1`** (`Dockerfile:13`) — логи uvicorn пишутся в stdout без буферизации (важно для `docker logs`).
8. **`EXPOSE 8000`** (`Dockerfile:15`) — документирующая декларация порта.
9. **CMD** (`Dockerfile:16`) — `uvicorn app.main:app --host 0.0.0.0 --port 8000`. Слушает на всех интерфейсах внутри контейнера; наружу порт пробрасывается через compose (см. §3).

> [!NOTE]
> В образе **нет** `cloudflared` и нет дополнительного процесс-менеджера: контейнер запускает единственный процесс uvicorn. Туннель Cloudflare к деплою отношения не имеет — это только локальный инструмент разработчика (см. §7).

---

## 3. `docker-compose.yml` — один сервис

Актуальное содержимое (`docker-compose.yml:1`–`docker-compose.yml:8`):

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

| Поле | Значение | Зачем |
|---|---|---|
| `build: .` | сборка из локального `Dockerfile` | используется **только локально** (`make up` с `--build`). На сервере исходников нет — там лежит лишь скопированный `docker-compose.yml`, поэтому реально образ **подтягивается** из GHCR, а не собирается |
| `image:` | `ghcr.io/zebaro24/sync-mate-api-ws:latest` | имя образа: локально — тег для собранного образа; на сервере — что пуллить с `--pull always` |
| `container_name` | `sync-mate-api-ws` | фиксированное имя контейнера |
| `restart: unless-stopped` | автоперезапуск | контейнер сам поднимается после падения/перезагрузки хоста, кроме явной ручной остановки |
| `ports` | `${SERVER_PORT:-8000}:8000` | внешний порт берётся из переменной `SERVER_PORT`, по умолчанию `8000`; внутри контейнера всегда `8000` |

> [!IMPORTANT]
> **Drift-замечание.** Раньше здесь было два сервиса (приложение + `cloudflared`-сайдкар, пробрасывавший трафик через туннель). Сейчас сервис **один**. Публичный доступ к проду (`https://sync-mate-api-ws.zebaro.dev`) обеспечивается инфраструктурой на самом сервере (reverse-proxy / туннель вне этого compose), а не вторым контейнером отсюда. Не «возвращайте» `cloudflared` в compose, считая его пропавшим — он удалён сознательно (`f0c7443`).

> [!NOTE]
> На сервере используется имя проекта compose `-p sync-mate` (см. `cd.yml:89` и `Makefile`), а не имя каталога. Держите его одинаковым везде, иначе compose создаст «второй» набор ресурсов вместо обновления существующих.

---

## 4. CI — `.github/workflows/ci.yml`

### Триггеры

```yaml
on:
  push:
    branches: [ main, master ]
  pull_request:
    branches: [ main, master ]
```

CI запускается на **каждый push** в `main`/`master` и на **каждый pull request** в эти ветки (`ci.yml:3`–`ci.yml:7`). CI **ничего не деплоит** — только проверяет.

### Jobs

Четыре независимых параллельных job. Каждый: checkout → setup Python `3.13` → кеш Poetry → установка Poetry `1.8.0` (`abatilo/actions-poetry@v3`) → `poetry install --no-interaction` → проверки.

| Job | Имя | Шаги проверки | Команды |
|---|---|---|---|
| `lint-format` | Lint & Format | формат + линт | `black --check app tests`, `isort --check-only app tests`, `flake8 app tests` (`ci.yml:40`–`ci.yml:46`) |
| `type-check` | Type Checking | статическая типизация | `mypy app` (`ci.yml:78`–`ci.yml:79`) |
| `security` | Security Audit | аудит безопасности | `bandit -r app`, `safety check` (`ci.yml:111`–`ci.yml:116`) |
| `test` | Tests & Coverage | тесты + покрытие | `pytest --cov=app --cov-report=xml --cov-report=term-missing`, затем загрузка в Codecov (`ci.yml:151`–`ci.yml:158`) |

### Версия Python — ТОЛЬКО 3.13

> [!IMPORTANT]
> **Drift-замечание.** CI тестирует на **одной** версии Python — `3.13` (`ci.yml:19`, `ci.yml:57`, `ci.yml:90`, `ci.yml:130`). Матрицы `3.11 / 3.12 / 3.13` **нет** (она была убрана в коммите «Test only on Python 3.13»). Если старый `DOCUMENTATION.md` упоминает несколько версий — это устарело. `pyproject.toml` объявляет `python = "^3.11"` как нижнюю границу совместимости, но проверяется и собирается только под 3.13.

### Окружение и секреты в CI

| Переменная | Где | Назначение |
|---|---|---|
| `PYTHONPATH: .` | job `test` (`ci.yml:122`) | чтобы `pytest` видел пакет `app` |
| `PROXIES_LIST` | job `test`, из `secrets.PROXIES_LIST` (`ci.yml:123`) | список прокси для тестов, ходящих к Rezka |

### Особенности и подводные камни CI

- **Кеш Poetry** (`actions/cache@v3`) ключуется по хешу `poetry.lock` (`ci.yml:21`–`ci.yml:30`). При смене зависимостей кеш инвалидируется автоматически.
- **`fail_ci_if_error: true`** у Codecov (`ci.yml:158`) — job `test` **падает**, если не удалось загрузить отчёт о покрытии (например, проблемы на стороне Codecov), даже если сами тесты зелёные. Это сознательный строгий режим.
- **Несогласованности версий action’ов** (мелочь, но полезно знать при отладке): job `security` использует `actions/setup-python@v4` (`ci.yml:88`), а остальные — `@v5`. Это не ошибка, просто разнобой.
- **Poetry в CI зафиксирован `1.8.0`**, в `Dockerfile` — нет (см. §2). Сборка образа и CI используют разные версии Poetry.
- `safety check` — устаревшая подкоманда `safety`; запускается как есть (`ci.yml:115`–`ci.yml:116`). Если падает на депрекейте — это про инструмент, а не про код.

---

## 5. CD — `.github/workflows/cd.yml`

### Триггер — ТОЛЬКО теги `v*`

```yaml
on:
  push:
    tags:
      - 'v*'
```

CD запускается **исключительно** при пуше тега вида `v*` (`cd.yml:3`–`cd.yml:6`). Обычный push в ветку CD **не** запускает.

> [!IMPORTANT]
> **Push в ветку = только CI. Пуш тега `v*` = продакшн-деплой.** Это водораздел: код в `main` сам по себе никуда не выкатывается; выкатывает именно тег.

Два последовательных job: `build-and-push` → (`needs`) → `deploy`.

### Job 1 — `build-and-push`

`permissions: contents: read, packages: write` (`cd.yml:11`–`cd.yml:13`) — нужно право писать в GHCR.

Шаги (`cd.yml:14`–`cd.yml:54`):

1. **Checkout** (`actions/checkout@v3`).
2. **Set version** (`cd.yml:19`–`cd.yml:26`): из `GITHUB_REF` берётся имя тега, отрезается префикс `v`:
   ```bash
   VERSION=${GITHUB_REF##*/}   # refs/tags/v1.2.3 -> v1.2.3
   VERSION=${VERSION#v}        # v1.2.3 -> 1.2.3
   ```
   Результат кладётся в `GITHUB_ENV` и `GITHUB_OUTPUT`. То есть версия образа **берётся из тега**, а не из `pyproject.toml`/`config.py`.
3. **Set repository name** (`cd.yml:29`–`cd.yml:35`): owner и имя репозитория приводятся к нижнему регистру → `zebaro24` и `sync-mate-api-ws`. GHCR требует lowercase.
4. **Log in to GHCR** (`docker/login-action@v2`, `cd.yml:38`–`cd.yml:43`): логин в `ghcr.io` под `github.actor` с автоматическим `secrets.GITHUB_TOKEN`.
5. **Build and push** (`cd.yml:46`–`cd.yml:54`): собирается образ и пушится в двух тегах:
   ```bash
   docker build -f Dockerfile -t ghcr.io/$OWNER_NAME/$REPO_NAME:${VERSION} .
   docker push  ghcr.io/$OWNER_NAME/$REPO_NAME:${VERSION}
   docker tag   ghcr.io/$OWNER_NAME/$REPO_NAME:${VERSION} \
                ghcr.io/$OWNER_NAME/$REPO_NAME:latest
   docker push  ghcr.io/$OWNER_NAME/$REPO_NAME:latest
   ```
   Итог: в GHCR появляются **два тега** — конкретная версия (например `:1.2.3`) и подвижный **`:latest`**. Именно `:latest` пуллит сервер (его прописывает `docker-compose.yml`).

### Job 2 — `deploy`

```yaml
deploy:
  needs: build-and-push
  environment:
    name: prod
    url: https://sync-mate-api-ws.zebaro.dev
```

Запускается только после успешного `build-and-push` (`cd.yml:58`). Привязан к GitHub-окружению **`prod`** с URL **`https://sync-mate-api-ws.zebaro.dev`** (`cd.yml:59`–`cd.yml:61`) — этот URL показывается в интерфейсе деплоев и подтверждает: тег `v*` ⇒ прод.

Шаги (`cd.yml:62`–`cd.yml:91`):

1. **Sparse checkout** (`actions/checkout@v3`, `cd.yml:63`–`cd.yml:67`): забирается **только** `docker-compose.yml` (`sparse-checkout`, `fetch-depth: 1`). Остальной исходник на сервер не едет.
2. **Copy docker-compose** (`appleboy/scp-action@v0.1.3`, `cd.yml:68`–`cd.yml:76`): по SCP файл `docker-compose.yml` копируется на сервер в каталог **`/srv/sync-mate/`**.
3. **Deploy via docker-compose** (`appleboy/ssh-action@v0.1.6`, `cd.yml:77`–`cd.yml:91`): по SSH на сервере выполняется:
   ```bash
   cd /srv/sync-mate
   docker login ghcr.io -u <github.actor> -p <GITHUB_TOKEN>
   export SERVER_PORT=<vars.SERVER_PORT>
   docker compose -p sync-mate up -d --pull always
   docker image prune -f
   ```
   - `docker login` — чтобы пуллить приватный образ из GHCR.
   - `export SERVER_PORT` — пробрасывает внешний порт в `docker-compose.yml` (переменная `${SERVER_PORT:-8000}`).
   - **`up -d --pull always`** — ключевой момент: `--pull always` заставляет compose **скачать свежий `:latest`** перед стартом, даже если локально уже есть образ с таким тегом. Без этого сервер запустил бы старый закешированный образ. Имя проекта — `-p sync-mate`.
   - `docker image prune -f` — чистит «повисшие» (dangling) образы после обновления, чтобы диск не забивался старыми слоями.

> [!NOTE]
> На сервере **нет исходников и нет `Dockerfile`** — только `docker-compose.yml`. Поэтому строка `build: .` на сервере не работает «по-настоящему»: деплой целиком полагается на готовый образ из GHCR и `--pull always`. Менять Dockerfile без выпуска нового тега бесполезно — на прод попадёт только то, что собрал `build-and-push`.

### Требуемые секреты и переменные

| Имя | Тип | Где используется | Назначение |
|---|---|---|---|
| `SERVER_HOST` | secret | `cd.yml:71`, `cd.yml:80` | хост сервера для SCP/SSH |
| `SERVER_USER` | secret | `cd.yml:72`, `cd.yml:81` | SSH-пользователь |
| `SSH_PRIVATE_KEY` | secret | `cd.yml:73`, `cd.yml:82` | приватный ключ для SSH/SCP |
| `SERVER_PORT` | **variable** (`vars.`) | `cd.yml:87` | внешний порт публикации контейнера на сервере |
| `PROXIES_LIST` | secret | `ci.yml:123` (CI) | список прокси к Rezka (в тестах) |
| `GITHUB_TOKEN` | автоматический | `cd.yml:43`, `cd.yml:85` | логин в GHCR (выдаётся Actions, заводить вручную не нужно) |

> [!NOTE]
> `SERVER_PORT` — это **repository/environment variable** (`vars.SERVER_PORT`), а не secret. Остальные три (`SERVER_HOST`, `SERVER_USER`, `SSH_PRIVATE_KEY`) — secrets. Если деплой падает на этапе SCP/SSH — первым делом проверьте, что заданы все три secret’а и что variable `SERVER_PORT` существует (иначе `export SERVER_PORT=` подставит пустую строку, и `${SERVER_PORT:-8000}` откатится на `8000`).

---

## 6. Полный поток «релиз → прод», шаг за шагом

```
git tag vX.Y.Z + git push origin vX.Y.Z
        │
        ▼
 cd.yml (триггер push tags v*)
        │
        ├─ build-and-push
        │     ├─ version = X.Y.Z (из тега)
        │     ├─ docker build -t ghcr.io/zebaro24/sync-mate-api-ws:X.Y.Z
        │     ├─ docker push  …:X.Y.Z
        │     └─ docker push  …:latest
        │
        ▼ (needs)
        └─ deploy (environment: prod → https://sync-mate-api-ws.zebaro.dev)
              ├─ scp docker-compose.yml → /srv/sync-mate/
              └─ ssh: docker login ghcr.io
                      docker compose -p sync-mate up -d --pull always
                      docker image prune -f
```

Итог: новый контейнер `sync-mate-api-ws` поднят из свежего `:latest`, доступен на `https://sync-mate-api-ws.zebaro.dev`.

---

## 7. Система управления релизами — деплой только через `/release`

> [!IMPORTANT]
> **Никогда не ставьте и не пушьте тег `v*` вручную.** Деплой выполняется только через owner-триггерный скилл **`/release`** (`.claude/skills/release/SKILL.md` в корне воркспейса). Ручной тег = неконтролируемый прод-деплой в обход строгих проверок и approve-маркеров.

Как это устроено (см. `scripts/release.py` и скилл `/release`):

1. `scripts/release.py --repo api --bump patch|minor|major` (или `--set X.Y.Z`):
   - проверяет, что репозиторий на `main` и дерево чистое;
   - вычисляет следующую версию из **последнего git-тега `v*`**;
   - прогоняет **строгий гейт** (`scripts/gate.py --repo api --strict`: lint + типы + протокол + тесты) — при «красном» **прерывается**;
   - бампит версии: `app/config.py` (поле `version`) и `pyproject.toml` (`[tool.poetry] version`);
   - дописывает секцию в `CHANGELOG.md`;
   - делает коммит `Release vX.Y.Z` и **локальный** annotated-тег — **без пуша**.
2. Скилл `/release` после одного явного подтверждения создаёт approve-маркеры (`.claude/.approve-push`, `.claude/.approve-deploy`) и пушит `main` и тег. Пуш тега и **запускает** `cd.yml`.

Таким образом версия в `pyproject.toml`/`config.py`, имя git-тега и тег Docker-образа держатся согласованными: тег задаёт версию образа в `cd.yml`, а `release.py` синхронно бампит файлы версий. На момент написания последний выпущенный тег — `v0.2.1`.

> [!NOTE]
> Версии в `pyproject.toml` (`0.1.0`) и `app/config.py` (`0.1.1`) могут отставать от последнего git-тега, если файлы редактировались помимо `release.py`. Доверяйте git-тегу как источнику истины для версии образа — именно из него `cd.yml` берёт `VERSION`.

---

## 8. Локальная разработка — `Makefile`

`Makefile` подключает `.env` (`include .env` + `export`) и определяет `PORT ?= 8000`.

| Цель | Команда | Что делает |
|---|---|---|
| `up` | `docker compose -p sync-mate up -d --build` | собрать и поднять контейнер локально (с `--build`, в отличие от прода) |
| `down` | `docker compose -p sync-mate down` | остановить и удалить контейнер |
| `logs` | `docker compose -p sync-mate logs -f` | хвост логов |
| `dev` | `poetry run uvicorn app.main:app --host 0.0.0.0 --port $(PORT) --reload` | uvicorn с авто-перезагрузкой, без Docker |
| `tunnel` | `cloudflared tunnel --no-autoupdate run --token $(CLOUDFLARE_TUNNEL_TOKEN)` | поднять именованный Cloudflare-туннель (токен из `.env`) |
| `tunnel-quick` | `cloudflared tunnel --url http://localhost:$(PORT)` | быстрый временный туннель со случайным `*.trycloudflare.com` |
| `run` | uvicorn + cloudflared параллельно (`trap 'kill 0' INT`) | запустить сервер и туннель вместе; Ctrl+C гасит оба |

> [!IMPORTANT]
> **`cloudflared` — это только локальное удобство разработчика** (`Makefile:22`–`Makefile:36`), способ показать локальный сервер наружу без публикации. К продакшн-деплою (`cd.yml`) он **не имеет отношения** и из `docker-compose.yml` удалён. Не путайте локальный туннель с тем, как прод раздаётся снаружи.

> [!NOTE]
> Локальный `make up` **собирает** образ из исходников (`--build`), а прод-деплой образ **пуллит** (`--pull always`). Это разные пути: локально вы тестируете свой код, на проде крутится то, что собрал `build-and-push` по тегу.

---

## 9. Переменные окружения (только имена)

> [!WARNING]
> Содержимое `.env` (реальные секреты, в т. ч. токен Cloudflare) **не читать и не печатать**. Ниже — только имена переменных.

**Конфигурация приложения** (`app/config.py`, класс `Settings`, читается из `.env`):

| Имя | Назначение |
|---|---|
| `DEBUG` | флаг отладки (по умолчанию `false`) |
| `REQUIRED_DOWNLOAD_TIME` | порог буферизации, сек (по умолчанию 15) |
| `REZKA_URL` | базовый URL Rezka (по умолчанию `https://rezka.ag`) |
| `PROXIES_LIST` | CSV-строка прокси; `Settings.__init__` сам разбивает её по запятой в список |

**Инфраструктура / деплой / локалка:**

| Имя | Где | Назначение |
|---|---|---|
| `SERVER_PORT` | `docker-compose.yml`, `cd.yml` (`vars`) | внешний порт публикации контейнера |
| `PORT` | `Makefile` | порт для локального uvicorn/туннеля (по умолчанию 8000) |
| `CLOUDFLARE_TUNNEL_TOKEN` | `Makefile`, `.env` | токен Cloudflare-туннеля (**только локально**) |
| `SERVER_HOST`, `SERVER_USER`, `SSH_PRIVATE_KEY` | `cd.yml` (secrets) | доступ к серверу по SSH/SCP |
| `PROXIES_LIST` | `ci.yml` (secret), `.env` | прокси к Rezka |
| `GITHUB_TOKEN` | `cd.yml` (авто) | логин в GHCR |

---

## 10. Частые проблемы и нюансы

- **Запушил в `main`, а деплоя нет.** Так и задумано: push запускает только `ci.yml`. Деплой — только по тегу `v*` через `/release`.
- **Тег запушен, но прод не обновился.** Проверьте, что job `deploy` дошёл до конца и что `--pull always` реально скачал новый `:latest`. Если `build-and-push` упал — `deploy` не стартует (`needs`).
- **`deploy` падает на SCP/SSH.** Чаще всего — не заданы secrets `SERVER_HOST`/`SERVER_USER`/`SSH_PRIVATE_KEY` или сервер недоступен. Каталог назначения — `/srv/sync-mate/`, он должен существовать и быть доступен `SERVER_USER`.
- **Контейнер слушает не на том порту.** Внутри всегда `8000`; снаружи — `SERVER_PORT`. Если variable `SERVER_PORT` не задана, на сервере подставится пустая строка в `export`, и сработает дефолт `8000` из `${SERVER_PORT:-8000}`.
- **CI зелёный локально, красный в Actions из-за Codecov.** `fail_ci_if_error: true` (`ci.yml:158`) роняет job `test` при сбое загрузки покрытия. Это не баг тестов.
- **Сборка образа отличается от CI.** В `Dockerfile` Poetry не запинен (последний с PyPI), в CI — `1.8.0`. При странных расхождениях зависимостей смотрите сюда.
- **Образ не пуллится на сервере.** Нужен `docker login ghcr.io` (делается в `cd.yml:85`) и право `packages: write`/`read`. Образ в GHCR должен существовать под `:latest`.
- **Не «чините» отсутствие `cloudflared` в compose.** Он удалён сознательно (`f0c7443`); прод раздаётся инфраструктурой сервера.

---

## См. также

- [`../CLAUDE.md`](../CLAUDE.md) — гид по бэкенд-части (стек, слои, запуск, race conditions).
- [`../../CLAUDE.md`](../../CLAUDE.md) — общий гид по репозиторию Sync-Mate (раздел «Что НЕ делать без явного запроса»: не пушить, не трогать `.env`).
- [`../../Sync-Mate-Extension/CLAUDE.md`](../../Sync-Mate-Extension/CLAUDE.md) — гид по расширению (его релиз идёт через `release.yml` → GitHub Release).
- [`../../DOCUMENTATION.md`](../../DOCUMENTATION.md) — полная техдокументация и WS-протокол. **Внимание:** раздел про деплой устарел (старая схема с `cloudflared` в compose) — ориентируйтесь на этот файл.
- `.claude/skills/release/SKILL.md` и `scripts/release.py` (корень воркспейса) — система выпуска релизов (`/release`).
