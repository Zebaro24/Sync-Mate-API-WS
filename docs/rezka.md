# Rezka — справочник по интеграции

Исчерпывающее описание модуля `app/modules/rezka`: как Sync-Mate-API-WS ходит на `rezka.ag`, парсит HTML/AJAX-ответы и декодирует обфусцированные URL видеопотоков.

---

## 1. Назначение и состав модуля

Модуль `app/modules/rezka` — единственный мост между бэкендом и публичным сайтом `rezka.ag`. Он решает три задачи:

1. **Поиск и метаданные** фильмов/сериалов (скрейпинг HTML и AJAX-эндпоинтов Rezka).
2. **Получение источников видео** (`.mp4`-ссылки на CDN) — с расшифровкой обфускации.
3. **Парсинг структуры сериала** (сезоны → эпизоды).

| Файл | Роль |
|---|---|
| `app/modules/rezka/_base.py` | Базовый HTTP-слой: `RezkaBase` — async-запросы через `httpx.AsyncClient`, прокси, парсинг ответа. |
| `app/modules/rezka/service.py` | `RezkaService` (поиск/инфо) и `RezkaStream` (источники видео). Вся бизнес-логика и парсинг. |
| `app/modules/rezka/_decoder.py` | `StreamDecoder` — алгоритм расшифровки обфусцированной строки плейлиста. |
| `app/modules/rezka/schemas.py` | Pydantic-модели ответов (контракт REST API). |
| `app/modules/rezka/dependencies.py` | DI-провайдеры: синглтоны `RezkaService` / `RezkaStream`. |
| `app/modules/rezka/router.py` | FastAPI-роутер, монтируется под `/api/rezka`. |

Иерархия классов: `RezkaService` и `RezkaStream` оба наследуются от `RezkaBase` (`service.py:24`, `service.py:142`).

---

## 2. Правило «только async» (жёсткое)

> Все методы `RezkaBase` / `RezkaService` / `RezkaStream` — **async**. HTTP идёт исключительно через `httpx.AsyncClient`. Синхронных вариантов нет и быть не должно.

Источник правила — `_request` в `_base.py:31-48`:

```python
async def _request(self, method, url, *, params=None, data=None, is_json=False):
    proxy = self._get_random_proxy()
    async with httpx.AsyncClient(proxy=proxy, timeout=_DEFAULT_TIMEOUT, follow_redirects=True) as client:
        try:
            response = await client.request(method, self.URL.join(url), params=params, data=data)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Rezka %s %s failed: %s", method, url, exc)
            raise
    return self._parse_response(response, is_json)
```

Следствия, которые нельзя нарушать:

- Публичные обёртки `get` (`_base.py:56-57`) и `post` (`_base.py:65-66`) — тоже `async` и просто делегируют в `_request`.
- Все методы `RezkaService` / `RezkaStream` объявлены `async def` и внутри `await self.get(...)` / `await self.post(...)`.
- **Роутеры обязаны `await`.** Каждый эндпоинт в `router.py` пишет `return await service.method(...)` / `return await stream.method(...)` (`router.py:24`, `:33`, `:41`, `:49`, `:58`, `:69`). Забыть `await` — значит вернуть корутину вместо данных и получить ошибку сериализации Pydantic.
- Запрещено возвращать синхронный `httpx` (см. `Sync-Mate-API-WS/CLAUDE.md`, раздел «Что НЕ делать»). Перевод на `AsyncClient` сделан сознательно — событийный цикл FastAPI/WS не должен блокироваться сетевым I/O к Rezka.

### Типобезопасность через `@overload`

`get` и `post` имеют по два `@overload` (`_base.py:50-54`, `:59-63`): при `is_json=False` (по умолчанию) возвращается `BeautifulSoup`, при `is_json=True` — `dict`. Это позволяет mypy выводить корректный тип результата без `cast` на стороне вызова. Реальный выбор делает `_parse_response` (`_base.py:25-29`): `response.json()` для JSON, иначе `BeautifulSoup(response.text, "html.parser")`.

---

## 3. `RezkaBase` — HTTP-слой

### 3.1 Конфигурация класса

| Атрибут / константа | Где | Значение / источник |
|---|---|---|
| `URL` | `_base.py:17` | `httpx.URL(settings.REZKA_URL)` — базовый адрес (по умолчанию `https://rezka.ag`, см. `app/config.py:19`). |
| `PROXIES_LIST` | `_base.py:18` | `settings.PROXIES_LIST` — список прокси (см. §6). |
| `_DEFAULT_TIMEOUT` | `_base.py:13` | `httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)`. Подобран под медленный публичный `rezka.ag`. |

Запросы выполняются с `follow_redirects=True` (`_base.py:41`) — Rezka любит редиректить (например, между зеркалами/слешами). Целевой URL собирается через `self.URL.join(url)` (`_base.py:43`): относительный путь (`/engine/ajax/...`) приклеивается к базе; абсолютный `movie_url` тоже корректно обрабатывается `httpx.URL.join`.

### 3.2 `get_text` — безопасное извлечение текста

`get_text` (`_base.py:68-72`) — статический помощник: `None` → `None`, иначе `str(tag.text).strip()`. Используется повсеместно в `service.py`, чтобы парсинг не падал на отсутствующих узлах DOM.

### 3.3 Жизненный цикл клиента (gotcha)

`AsyncClient` создаётся **на каждый запрос** (`_base.py:41`, внутри `async with`). Последствия:

- Прокси выбирается заново для **каждого** запроса (см. §6) — нет «залипания» на одном прокси в рамках сессии.
- Нет переиспользования соединений между запросами: пул (`pool=5.0` в таймауте) живёт только в пределах одного `with`-блока, так что keep-alive между вызовами не работает. Это осознанный компромисс ради простоты и ротации прокси, а не баг.

---

## 4. `RezkaService` — поиск и метаданные

Все методы возвращают Pydantic-модели из `schemas.py`. Ниже — что и как парсится. **Важно:** весь парсинг основан на CSS-селекторах и регулярках по HTML Rezka — это структурно хрупко (см. §7).

### 4.1 `quick_search` — `service.py:25-47`

- **Запрос:** `POST /engine/ajax/search.php`, `data={"q": movie_name}` → HTML-фрагмент.
- **Парсинг:** перебор `li a`; из `href` извлекается id регуляркой `/(\d+)-` (`service.py:33`). Если совпадения нет — строка пропускается (Rezka подмешивает разделители без id, `service.py:34-36`).
- `alter_title` берётся из `title_elem.next_sibling` (`service.py:42`).
- **Возврат:** `List[MovieQuickSearchResponse]`.

### 4.2 `quick_info_movie` — `service.py:49-66`

- **Запрос:** `POST /engine/ajax/quick_content.php`, `data={"id": movie_id, "is_touch": 1}` → HTML.
- **Жанры:** из **последнего** блока `.b-content__bubble_text` берутся `<a>` (`service.py:55-58`). Если блоков нет — пустой список без падения.
- **Возврат:** `QuickInfoMovieResponse`.

### 4.3 `search` — `service.py:68-88`

- **Запрос:** `GET /search/`, `params={"do": "search", "subaction": "search", "q": movie_name}` → HTML.
- **Парсинг:** `div.b-content__inline_item` с параметром `limit=limit` у `soup.select` (`service.py:75`). **Особенность:** `limit=0` (значение по умолчанию из роутера) в BeautifulSoup трактуется как «без ограничения» (0 — falsy), то есть возвращаются все найденные элементы.
- `id` обязателен: `int(movie_elem["data-id"])` (`service.py:80`) — отсутствие атрибута приведёт к `KeyError` → 500.
- **Возврат:** `List[MovieSearchResponse]`.

### 4.4 `info_movie` — `service.py:90-139`

Самый сложный парсер. Шаги:

1. **Запрос:** `GET {movie_url}` → HTML (`service.py:91`).
2. **Идентификация плеера через inline-JS** (`service.py:93-107`): склеиваются тексты всех `<script>` и ищется регулярка
   ```
   sof\.tv\.(initCDNMoviesEvents|initCDNSeriesEvents)\((\d+),\s?(\d+),
   ```
   - `initCDNMoviesEvents` → `content_type = "movie"`, `initCDNSeriesEvents` → `"series"`.
   - Из совпадения берутся `movie_id` и `translate_id` (id переводчика по умолчанию).
   - **Фолбэк** (`service.py:102-107`): если JS не найден, `movie_id` извлекается из URL регуляркой `/(\d+)-`; при неудаче — `ValueError` («Cannot extract movie_id from URL») → 500. `content_type` и `translate_id` становятся `None`.
3. **Рейтинги** IMDb/KP (`service.py:109-115`): из `span.b-post__info_rates.imdb` / `.kp`.
4. **Жанры** (`service.py:117`): `span[itemprop="genre"]`.
5. **Переводчики** (`service.py:119-126`): из `li.b-translator__item, a.b-translator__item` по атрибуту `data-translator_id`. Если переводчиков нет, но `translate_id` известен из JS — кладётся `{translate_id: None}`.
6. **Возврат:** `InfoMovieResponse` (`service.py:128-139`).

---

## 5. `RezkaStream` + `StreamDecoder` — источники видео

### 5.1 `get_movie_source` — `service.py:143-152`

```python
async def get_movie_source(self, movie_id: int, translator_id: int) -> MovieResponse:
    response = await self.post(
        "/ajax/get_cdn_series/",
        data={"id": movie_id, "translator_id": translator_id, "action": "get_movie"},
        is_json=True,
    )
    url_value = response.get("url")
    if not isinstance(url_value, str):
        raise ValueError(f"url must be str, got {type(url_value).__name__}")
    return MovieResponse(urls=StreamDecoder.decode(url_value))
```

- **Запрос:** `POST /ajax/get_cdn_series/`, `action=get_movie`, `is_json=True`.
- Поле `url` из JSON — обфусцированная строка плейлиста; проверяется, что это `str` (иначе `ValueError` → 500), и отдаётся в `StreamDecoder.decode`.
- **Возврат:** `MovieResponse(urls={качество: mp4_url})`.

### 5.2 `get_series_source` — `service.py:154-190`

- **Запрос:** тот же `POST /ajax/get_cdn_series/`, но `action=get_episodes`, `is_json=True`. Поля `season`/`episode` добавляются в `data` только если переданы и truthy (`service.py:162-165`).
- JSON-ответ содержит **HTML-фрагменты** в строковых полях `seasons`, `episodes`, плюс обфусцированный `url`.
- Парсинг сезонов/эпизодов — см. §5.3.
- **Возврат:** `SeriesResponse(seasons={season_id: [episode_ids]}, urls={качество: mp4_url})`.

### 5.3 Алгоритм декодирования URL (`_decoder.py`) — пошагово

Rezka намеренно обфусцирует строку плейлиста, чтобы помешать скрейпингу. `StreamDecoder.decode` (`_decoder.py:26-49`) разворачивает её.

**Константы** (`_decoder.py:6-14`):

| Константа | Значение | Назначение |
|---|---|---|
| `_STREAM_SEPARATOR` | `"//_//"` | Разделитель-мусор, вставленный внутрь base64. |
| `_TRASH_LIST` | `["$$#!!@#!@##", "^^^!@##!!##", "####^!!##!@@", "@@@@@!##!^^^", "$$!!@$$@^!@#$$@"]` | «Мусорные» строки; в поток подмешаны их **base64-представления**. |
| `_QUALITY_PATTERN` | `^\[(\d+p(?:\s\w*)?)\]` | Метка качества в начале части: `[360p]`, `[1080p]`, `[1080p Ultra]`. |

**Шаг 1. `decode` — валидация** (`_decoder.py:28-35`):
- Пустая строка → `ValueError("base64_encoded_stream cannot be empty")`.
- Вызов `_decode_stream_base64`; любое исключение внутри оборачивается в общий `Exception("Error during decoding: ...")` (`_decoder.py:34-35`).

**Шаг 2. `_decode_stream_base64` — снятие обфускации** (`_decoder.py:16-24`):
1. **Отрезается префикс из 2 символов**: `stream_encoded = stream_encoded[2:]` (`_decoder.py:18`). Rezka добавляет 2-символьный маркер в начало (исторически вида `#h`). Длина зашита жёстко — см. §7.
2. **Двойной проход** `for _ in range(2)` (`_decoder.py:19`):
   - Удаляются **все** вхождения `//_//` (`_decoder.py:20`).
   - Для каждой мусорной строки из `_TRASH_LIST` вычисляется её base64 (`base64.b64encode(value.encode()).decode()`) и удаляются **все** вхождения этого base64 из потока (`_decoder.py:21-23`).
   - **Почему два прохода:** мусор и разделители могут быть вложены/перекрываться — удаление одного слоя обнажает новые вхаждения, которые подчищает второй проход.
3. **`base64.b64decode(...).decode()`** (`_decoder.py:24`) — после очистки остаётся валидный base64; декодируется в строку плейлиста вида:
   ```
   [360p]https://.../360.mp4 or https://mirror/.../360.mp4,[720p]https://.../720.mp4,[1080p]https://.../1080.mp4
   ```

**Шаг 3. `decode` — разбор плейлиста** (`_decoder.py:37-49`):
- Строка делится по `,` на части (`_decoder.py:38`).
- Каждая часть матчится `_QUALITY_PATTERN`; без совпадения — пропуск (`_decoder.py:39-41`).
- `quality = match.group(1)` (например `"1080p"` или `"1080p Ultra"`).
- **`"1080p Ultra"` пропускается** (`_decoder.py:43-44`) — это премиум/4K-вариант, ссылка обычно недоступна без подписки.
- Остаток части (после `]`) делится по `" or "` на зеркала; выбирается **первая** ссылка, оканчивающаяся на `.mp4` (`_decoder.py:45-46`). HLS/`.m3u8` игнорируются — нужен прямой прогрессивный mp4.
- Результат: `dict[str, str]` вида `{"360p": url, "720p": url, "1080p": url}`.

### 5.4 Парсинг сезонов и эпизодов (хрупкость)

`get_series_source` парсит два HTML-фрагмента (`service.py:169-185`):

**Сезоны** (`service.py:169-179`):
```python
season_elems = BeautifulSoup(str(response["seasons"]), "html.parser").select("li")
for elem in season_elems:
    sid_attr = elem.get("data-tab_id") or elem.get("data-season_id")
    if sid_attr is not None:
        seasons[int(str(sid_attr))] = []
        continue
    # Фолбэк: число из текста (устойчиво к смене локали)
    match = _SEASON_NUMBER_RE.search(elem.get_text())
    if match:
        seasons[int(match.group(0))] = []
```
- Сначала пытается прочитать атрибут `data-tab_id` или `data-season_id`.
- **Фолбэк** — `_SEASON_NUMBER_RE = re.compile(r"\d+")` (`service.py:21`): извлекает **первое число** из текста `<li>` (`service.py:177-179`). Это устойчиво к локали («Сезон 2» / «Season 2» / «2-й сезон» дают `2`), но остаётся хрупким к **структуре HTML**: если Rezka уберёт `<li>`, переименует атрибуты или изменит разметку — парсинг молча вернёт пустой/неполный результат.

**Эпизоды** (`service.py:181-185`): из `<li>` обязательно читаются `data-season_id` и `data-episode_id` (`service.py:183-184`) — оба обязательны, отсутствие → `KeyError` → 500. Эпизоды добавляются в `seasons` через `setdefault` (`service.py:185`), поэтому сезон может появиться даже если его не было во фрагменте `seasons`.

> **Гочи (см. `Sync-Mate-API-WS/CLAUDE.md`):** парсинг сезонов устойчив к локализации (regex по числу), но всё ещё хрупкий. При смене HTML-структуры Rezka ждите поломок именно здесь и в `info_movie`.

---

## 6. Прокси (`PROXIES_LIST`)

- **Источник:** `settings.PROXIES_LIST` → `RezkaBase.PROXIES_LIST` (`_base.py:18`).
- **Конфиг:** `app/config.py:21` объявляет `PROXIES_LIST: list | str | None = None`. В `Settings.__init__` (`config.py:25-28`) CSV-строка из окружения разбивается по запятой в список с `strip()`. То есть переменная окружения `PROXIES_LIST` задаётся как строка `proxy1,proxy2,...`.
- **Выбор:** `_get_random_proxy` (`_base.py:20-23`): если список пуст/`None` → `None` (прямое соединение), иначе `random.choice` (помечен `# nosec B311` — random не криптографический, и это ОК).
- **Применение:** на **каждый** запрос создаётся новый `AsyncClient(proxy=proxy, ...)` (`_base.py:40-41`) — прокси ротируется на каждый вызов.
- В CI прокси передаётся как секрет `PROXIES_LIST` в job `test` (`.github/workflows/ci.yml`).

> **Секреты:** значения прокси и прочих ключей живут в `.env` (в `.gitignore`). В документации перечисляются только **имена** переменных, не значения.

---

## 7. Обработка ошибок

| Источник ошибки | Где | Что происходит |
|---|---|---|
| Сетевая/HTTP-ошибка Rezka | `_base.py:44-47` | `response.raise_for_status()` бросает; ловится `except httpx.HTTPError`, логируется `logger.warning`, **пробрасывается дальше**. Роутеры не ловят → FastAPI отдаёт **500 Internal Server Error**. |
| Пустая обфусцированная строка | `_decoder.py:28-29` | `ValueError` → 500. |
| Ошибка декодирования base64/мусора | `_decoder.py:34-35` | Любое исключение оборачивается в `Exception("Error during decoding: ...")` → 500. |
| `url` не строка в `get_movie_source` | `service.py:150-151` | `ValueError` → 500. |
| Не извлечён `movie_id` в `info_movie` | `service.py:104-105` | `ValueError("Cannot extract movie_id from URL")` → 500. |
| Отсутствует обязательный атрибут (`data-id`, `data-season_id`, `data-episode_id`) | `service.py:80`, `:183-184` | `KeyError` → 500. |

Принцип: **ошибки Rezka не глушатся** — `httpx.HTTPError` намеренно превращается в 500, чтобы клиент видел недоступность Rezka, а не пустой ответ (см. `Sync-Mate-API-WS/CLAUDE.md`: «HTTP-ошибки rezka.ag пробрасываются как `httpx.HTTPError` — это превращается в 500. Не глушите без причины»). Единственное логирование — `warning` в `_request`; стектрейс 500 формирует FastAPI.

---

## 8. REST-эндпоинты (`router.py`)

Роутер создаётся с `tags=["Rezka"]` (`router.py:16`) и монтируется в `app/api/router.py` под префиксом `/rezka`, а весь API — под `/api` (`app/main.py:61`). Итоговый базовый путь — **`/api/rezka`**.

| Метод | Путь | Query-параметры | Ответ | Реализация |
|---|---|---|---|---|
| GET | `/api/rezka/quick_search` | `movie_title: str` | `List[MovieQuickSearchResponse]` | `router.py:19-24` → `service.quick_search` |
| GET | `/api/rezka/search` | `movie_title: str`, `limit: int = 0` | `List[MovieSearchResponse]` | `router.py:27-33` → `service.search` |
| GET | `/api/rezka/quick_info_movie` | `movie_id: int` | `QuickInfoMovieResponse` | `router.py:36-41` → `service.quick_info_movie` |
| GET | `/api/rezka/info_movie` | `movie_url: str` | `InfoMovieResponse` | `router.py:44-49` → `service.info_movie` |
| GET | `/api/rezka/movie_source` | `movie_id: int`, `translator_id: int` | `MovieResponse` | `router.py:52-58` → `stream.get_movie_source` |
| GET | `/api/rezka/series_source` | `series_id: int`, `translator_id: int`, `season: int\|None`, `episode: int\|None` | `SeriesResponse` | `router.py:61-69` → `stream.get_series_source` |

> **Нюанс именования:** query-параметр называется `movie_title` (`router.py:20`, `:29`), а метод сервиса принимает `movie_name` — это просто разные имена на двух слоях, не баг.

### DI-провайдеры (`dependencies.py`)

`RezkaService` и `RezkaStream` создаются как **модульные синглтоны** (`dependencies.py:3-4`); `get_rezka_service` / `get_rezka_stream` возвращают их (`dependencies.py:7-12`) и инжектятся через `Depends` (`router.py:22`, `:56` и т.д.). Синглтоны безопасны: состояние per-request отсутствует — `AsyncClient` создаётся внутри каждого `_request`, общих изменяемых полей нет.

---

## 9. Схемы ответов (`schemas.py`)

| Модель | Поля | Где |
|---|---|---|
| `MovieQuickSearchResponse` | `id:int`, `title:str`, `alter_title:str`, `rating:Optional[str]`, `url:str` | `schemas.py:6-11` |
| `QuickInfoMovieResponse` | `id:int`, `title:str`, `category:str`, `description:str`, `genres:List[str]`, `rating:Optional[str]` | `schemas.py:14-20` |
| `MovieSearchResponse` | `id:int`, `title:str`, `category:str`, `caption:str`, `image:str`, `url:str` | `schemas.py:23-29` |
| `InfoMovieResponse` | `id:int`, `title:str`, `alter_title:Optional[str]`, `category:str`, `description:str`, `genres:List[str]`, `rating:Optional[Dict[str,str]]`, `url:str`, `content_type:Optional[str]`, `translators:Dict[int, str\|None]` | `schemas.py:32-42` |
| `MovieResponse` | `urls:Dict[str,str]` (качество → mp4) | `schemas.py:45-46` |
| `SeriesResponse` | `seasons:Dict[int, List[int]]`, `urls:Dict[str,str]` | `schemas.py:49-51` |

---

## 10. Внутренние эндпоинты Rezka (что дёргаем на `rezka.ag`)

| Метод сервиса | Эндпоинт Rezka | HTTP | Формат ответа |
|---|---|---|---|
| `quick_search` | `/engine/ajax/search.php` | POST | HTML |
| `quick_info_movie` | `/engine/ajax/quick_content.php` | POST | HTML |
| `search` | `/search/` | GET | HTML |
| `info_movie` | `{movie_url}` (полный URL страницы) | GET | HTML |
| `get_movie_source` | `/ajax/get_cdn_series/` (`action=get_movie`) | POST | JSON |
| `get_series_source` | `/ajax/get_cdn_series/` (`action=get_episodes`) | POST | JSON (+ HTML-фрагменты внутри) |

---

## 11. Конфигурация (только имена переменных)

Читаются из `.env` через `pydantic-settings` (`app/config.py`). Значения **не** документируются.

| Имя переменной | Назначение | Дефолт |
|---|---|---|
| `REZKA_URL` | Базовый адрес Rezka | `https://rezka.ag` (`config.py:19`) |
| `PROXIES_LIST` | CSV-список прокси (разбирается в список) | `None` (`config.py:21`) |
| `REQUIRED_DOWNLOAD_TIME` | Используется логикой комнаты, не Rezka | `15` (`config.py:17`) |
| `debug` | Флаг отладки | `False` (`config.py:15`) |

> Деплой: `docker-compose.yml` содержит **один** сервис `sync-mate-api-ws` (контейнер `cloudflared` удалён). CI (`.github/workflows/ci.yml`) гоняет lint/type-check/security/tests **только на Python 3.13**. Не доверяйте устаревшим разделам корневого `DOCUMENTATION.md` по части деплоя — сверяйтесь с конфигами.

---

## 12. Шпаргалка по «хрупким местам»

- **Регулярки по HTML/JS** — основной риск: `info_movie` (`sof\.tv\....`, `service.py:93`), `quick_search`/`info_movie` (`/(\d+)-`), сезоны (`\d+`, `service.py:21`). Смена разметки Rezka ломает парсинг тихо (пустые результаты) или с `KeyError`/`ValueError` (500).
- **Префикс `[2:]`** в `_decode_stream_base64` (`_decoder.py:18`) — жёстко зашитая длина в 2 символа. Изменится маркер Rezka → декодирование сломается.
- **`_TRASH_LIST` / `_STREAM_SEPARATOR`** (`_decoder.py:6-13`) — захардкоженный «словарь мусора». Rezka меняет схему обфускации периодически; при поломке источников видео обновлять нужно именно здесь.
- **`1080p Ultra` исключается** (`_decoder.py:43-44`) — это ожидаемое поведение, не баг.
- **`limit=0` = без лимита** в `search` (`service.py:75`) — особенность BeautifulSoup.

---

## См. также

- [`../CLAUDE.md`](../CLAUDE.md) — гид по бэкенд-части (раздел «Rezka — особенности», «Что НЕ делать»).
- [`../../CLAUDE.md`](../../CLAUDE.md) — общий гид по репозиторию Sync-Mate.
- [`../../DOCUMENTATION.md`](../../DOCUMENTATION.md) — полная техническая документация (учтите: раздел про деплой частично устарел — сверяйтесь с конфигами).
- Прочие справочники в этом каталоге `docs/` (по мере появления: WS-протокол, доменная модель комнаты, деплой).
