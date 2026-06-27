# Протокол WebSocket — Sync-Mate

Единый канонический контракт реального времени между браузерным расширением (FE) и FastAPI-сервером (BE): рукопожатие, коды закрытия, все 9 типов сообщений, алгоритм синхронизации воспроизведения и жизненный цикл комнаты.

> **Перспектива: бэкенд.** Этот файл живёт в `Sync-Mate-API-WS/docs/`. Его зеркало с перспективой фронта — `Sync-Mate-Extension/docs/websocket-protocol.md`.
>
> **Канонические разделы §1–§6 в обоих файлах идентичны слово в слово.** Любая правка протокола обязана синхронно менять оба файла (см. §6). Раздел §7 — специфичен для этой стороны (бэкенд: какая функция что испускает/обрабатывает, `path:line`).

> Документ описывает **реальность кода** на момент написания. Корневой `DOCUMENTATION.md` частично устарел (особенно про деплой) — при расхождениях доверяйте этому файлу и исходникам.

---

## 1. Эндпоинт и рукопожатие

### 1.1. Эндпоинт

```
ws://{host}/ws/{room_id}      # локально:  ws://127.0.0.1:8000/ws/<room_id>
wss://{host}/ws/{room_id}     # за TLS
```

Роутер объявлен как `@router.websocket("/{room_id}")` и подключается с префиксом `/ws`, поэтому полный путь — `/ws/{room_id}`. `room_id` — это идентификатор уже **существующей** комнаты (создаётся заранее REST-запросом `POST /api/rooms`); WebSocket комнату не создаёт, только присоединяет к ней.

### 1.2. Рукопожатие

Обмен строго двухтактный — соединение бесполезно, пока не пройден этот шаг:

```jsonc
// 1. Клиент → сервер  (ПЕРВЫЙ кадр после открытия сокета, обязателен)
{ "type": "connect", "name": "Alice" }

// 2. Сервер → клиент  (подтверждение, выдаёт идентификатор пользователя)
{ "type": "connect", "id": "550e8400-e29b-41d4-a716-446655440000" }
```

Последовательность на сервере:

1. `await websocket.accept()` — сокет принимается всегда.
2. `room_service.get_room(room_id)`; если комнаты нет → **close 4000**.
3. Чтение первого кадра и его валидация как `ConnectMessage` (Pydantic). Любая ошибка (не JSON, нет `type`/`name`, `type != "connect"`) → **close 4001**.
4. Создаётся `User(name, websocket)` с новым `uuid4`, выполняется `await room.add_user(user)`.
5. Сервер отправляет `{"type":"connect","id": user.user_id}` и входит в основной цикл приёма.

`id` — UUID, сгенерированный сервером (`User.user_id = str(uuid4())`). Имя берётся **только** из кадра `connect`; смена ника в хранилище расширения на активную сессию не влияет до переподключения.

---

## 2. Коды закрытия

| Код | Когда | Сторона/причина |
|---|---|---|
| `4000` | `room_service.get_room(room_id)` вернул `None` | Комната не найдена. `reason="Room not found"`. Закрытие **до** рукопожатия. |
| `4001` | Первый кадр не прошёл валидацию `ConnectMessage` | `reason="Authentication is required"`. Не JSON / нет полей / `type != "connect"`. |
| `1011` | Необработанное исключение в основном цикле приёма | Внутренняя ошибка сервера (стандартный WS-код). Закрытие оборачивается в `try/except` — сокет мог уже быть закрыт клиентом. |
| *(норма)* | `WebSocketDisconnect` — клиент закрыл соединение | Кода ошибки нет; сервер только логирует и снимает пользователя. |

При **любом** исходе (нормальное закрытие, 1011, исключение) в блоке `finally` выполняется `await room.remove_user(user)` — пользователь всегда снимается из комнаты. `4000`/`4001` срабатывают до создания пользователя, поэтому снимать некого.

Автопереподключения протокол не предусматривает — это ответственность клиента. Комнаты не персистятся (in-memory `dict` в `RoomService`); перезапуск сервера рвёт все сессии.

---

## 3. Полная таблица сообщений (9 типов)

Поля `current_time` и `downloaded_time` — числа (секунды; на клиенте округляются). «Направление»: c→s (клиент→сервер), s→c (сервер→клиент), оба.

| Тип | Направление | Поля | Триггер | Эффект |
|---|---|---|---|---|
| `connect` | оба | c→s: `name`; s→c: `id` | Открытие сокета | Рукопожатие (§1.2). c→s обязателен первым; s→c подтверждает и выдаёт UUID. |
| `info` | оба | c→s: произвольные (`title`, `translator`, `episode?`, `season?`, `url`, …); s→c: `name`, `downloaded_time` (+ что было в `status`, кроме `current_time`) | c→s: смена видео/перевода/эпизода; s→c: ретрансляция чужого `status` | c→s: сохраняется в `user.info` (всё, кроме `type`). s→c: peers видят, кто и сколько забуферизировал. |
| `play` | оба | c→s: `current_time`, `downloaded_time`; s→c: *(полей нет)* | c→s: пользователь нажал play / домотал; s→c: все готовы | c→s: запрос воспроизведения. s→c: команда всем играть (рассылается, только когда «готовы все»). |
| `pause` | оба | c→s: `current_time`, `downloaded_time`; s→c: *(полей нет)* | c→s: пользователь нажал pause; s→c: пауза от соседа | c→s: запрос паузы. s→c: команда поставить паузу **остальным** (инициатору не шлётся). |
| `seek` | **s→c** | `current_time` | Выравнивание позиции (§4): отстающие в `check_is_loaded` + согласование при `play`/`pause` | Клиент перематывает плеер на `current_time`. **Клиент `seek` не отправляет** — его нет в `_VALID_ACTIONS`, такой кадр был бы проигнорирован. |
| `status` | **c→s** | `current_time`, `downloaded_time` | Heartbeat: буферизация плеера + внутренние `pause()`/`seek()` клиента | Сервер обновляет `user.current_time`/`downloaded_time`, проверяет готовность комнаты (§4) и ретранслирует кадр соседям как `info`. **Сервер `status` не шлёт.** |
| `load` | **c→s** | `current_time`, `downloaded_time` | Запрос пересинхронизации с позицией комнаты | Сервер фиксирует позицию и, если готовы все, отдаёт `play` или `remove_block_pause`. **Внимание:** в текущем FE-коде `load` не отправляется — тип зарезервирован в обоих enum ради паритета (§6). |
| `set_video` | оба | c→s: `video_url` **или** `url` (+ `current_time?`); s→c: `video_url`, `current_time` | c→s: сменить видео для всей комнаты; s→c: команда перейти на URL | c→s: сброс состояния комнаты + рассылка всем. s→c: клиент переходит (`location.href`) на новый URL. **Внимание:** текущий FE только принимает `set_video`, сам его не шлёт. |
| `remove_block_pause` | **s→c** | *(полей нет)* | Комната на паузе, и подошедший клиент стал готов (`status`/`load`) | Снять блокировку-«замок» паузы на клиенте (скрыть оверлей), не запуская воспроизведение. |

### Асимметрии, которые легко упустить

- **`seek` — только s→c.** Когда пользователь сам перематывает, клиент шлёт `play`/`pause` (со своим `current_time`), а сервер выравнивает остальных через s→c `seek`.
- **`status` — только c→s.** Сервер никогда не шлёт `status`; он превращает его в `info` для соседей.
- **`load` и `set_video`** присутствуют в обоих enum, но в текущем FE как исходящие **не используются** (`load` не шлётся вообще; `set_video` FE только принимает). Их нельзя удалять — это сломает паритет §6 и REST-сценарий смены видео.

---

## 4. Алгоритм синхронизации — «никто не стартует, пока не готовы все»

Центральный инвариант: воспроизведение запускается только тогда, когда **у всех** участников совпадает позиция **и** набрано достаточно буфера. Иначе один отстающий навсегда блокировал бы запуск.

### 4.1. Состояние

- **Комната:** `current_time` (опорная позиция), `is_paused` (логическая пауза комнаты), `is_loaded` (все готовы).
- **Пользователь:** `current_time`, `downloaded_time` — обновляются на **каждом** входящем `status`/`play`/`pause`/`load`.
- **Порог:** `REQUIRED_DOWNLOAD_TIME` (по умолчанию **15** секунд) — сколько буфера впереди позиции обязан иметь каждый.

### 4.2. Проверка готовности (`check_is_loaded`)

Выполняется под `asyncio.Lock` (сериализация с `add_user`/`remove_user`):

1. **Коррекция отстающих.** Все, у кого `user.current_time != room.current_time`, получают s→c `seek` на `room.current_time`. Без этого один рассинхронизированный клиент блокировал бы старт навсегда.
2. **Готовы все?** `all_ready` истинно, когда участников ≥ 1 **и** для каждого: `current_time == room.current_time` **и** `downloaded_time >= REQUIRED_DOWNLOAD_TIME`.
3. Если `all_ready` → `is_loaded = True`; возвращается `all_ready`.

> Сравнение `current_time == room.current_time` — **точное** равенство `float`. Оно работает потому, что клиент округляет время перед отправкой, а опорная `room.current_time` берётся из того же присланного значения; рассогласование исправляет шаг 1 (`seek`).

### 4.3. Гейт `REQUIRED_DOWNLOAD_TIME`

`downloaded_time` — это сколько секунд впереди текущей позиции уже в буфере. Пока хотя бы у одного оно меньше порога — `all_ready = False`, команда `play` не уходит, клиенты держат «замок» паузы (оверлей загрузки). Это не даёт стартовать тому, кто не успел докачать.

### 4.4. Ход проверки по событиям

- **`status` (heartbeat):** если комната ещё не `is_loaded` → `check_is_loaded`. Стали готовы все → если `is_paused`: `remove_block_pause` (снять замок без старта), иначе `play` (старт всем).
- **`play`:** выровнять остальных (`seek` с позицией инициатора), `load(current_time)`, `is_paused=False`, и если готовы все → `play`.
- **`pause`:** выровнять остальных (`seek`), отправить им `pause`, `load(current_time)`, `is_paused=True`.
- **`load`:** `load(current_time)`; если готовы все → `remove_block_pause` (когда `is_paused`) или `play`.

`load(current_time)` всегда ставит `is_loaded=False` — любая смена позиции требует новой проверки готовности.

---

## 5. Жизненный цикл комнаты

```
СОЗДАНИЕ            REST POST /api/rooms  →  Room в RoomService (in-memory)
   │                video_url = текущая страница Rezka; current_time = 0
   ▼
ПОДКЛЮЧЕНИЕ         ws://host/ws/{room_id}  →  connect{name}  →  connect{id}
   │                add_user(user)
   ▼
HEARTBEAT          плеер шлёт status{current_time, downloaded_time}
   │                сервер: check_is_loaded → (play | remove_block_pause)
   │                сервер ретранслирует соседям как info{name, downloaded_time}
   ▼
УПРАВЛЕНИЕ          play / pause / seek(s→c) / load
   │                выравнивание позиции + гейт буфера (§4)
   ▼
СМЕНА ВИДЕО         set_video{video_url}  →  всем set_video  →  переход по URL
   │                state комнаты сбрасывается (is_loaded=False, is_paused=False)
   ▼
ВЫХОД              WebSocketDisconnect / close  →  finally: remove_user(user)
```

Замечания:

- **Создание** — это REST, не WS. WebSocket присоединяет к уже существующей комнате.
- **Heartbeat** двунаправлен по эффекту: продвигает машину готовности и одновременно кормит чужие info-панели.
- **Смена видео** ведёт к перезагрузке страницы у всех; после неё content-скрипт переинициализируется и заново проходит рукопожатие.
- **Очистки пустых комнат нет** — удаление только вручную через REST `DELETE`.

---

## 6. Критический инвариант: паритет BE ↔ FE

**Множество типов сообщений обязано быть идентичным на бэкенде и фронтенде.** Рассинхрон ломает синхронизацию комнаты молча — кадр незнакомого типа просто игнорируется.

Добавление / переименование / удаление типа требует правок **на обеих сторонах одновременно**:

**Бэкенд (`Sync-Mate-API-WS`):**
- `app/modules/room/handler.py` → `UserHandler._VALID_ACTIONS` (входящие действия) **И** соответствующий `_handle_*`/inline-ветка.
- `app/modules/room/models.py` / `handler.py` / `ws/router.py` → `send_json({"type": …})` (исходящие).
- `app/ws/schemas.py` → `ConnectMessage.type = Literal["connect"]` (рукопожатие).

**Фронтенд (`Sync-Mate-Extension`):**
- `src/features/room/model/messageTypes.ts` → `enum WSMessageTypes`.
- `src/features/room/RoomCoordinator.ts` → ветка обработки входящего типа и/или отправитель.

**Документация и автоматика:**
- `scripts/protocol_sync.py` — гейт паритета: извлекает все строковые `type` с обеих сторон и сверяет множества (exit 0 — синхронны, 1 — дрейф, 2 — файлы не найдены).
- Общий гейт `scripts/gate.py` (шаг `protocol`).
- Хук `.claude/hooks/guard-protocol.py`.
- Скилл `/sync-protocol`.
- Агент `protocol-guardian`.

> **Классическая ловушка:** строка добавлена в `_VALID_ACTIONS`, но `_handle_*` для неё нет → действие «молча принято» и **не имеет эффекта**. То же ловит `scripts/arch_lint_api.py`.

---

## 7. Перспектива бэкенда: где что испускается и обрабатывается

Все пути относительны корня `Sync-Mate-API-WS/`.

### 7.1. Рукопожатие и цикл (`app/ws/router.py`)

| Шаг | Место |
|---|---|
| `accept()` | `app/ws/router.py:22` |
| `get_room` → close `4000` | `app/ws/router.py:24-27` |
| Валидация `ConnectMessage` → close `4001` | `app/ws/router.py:29-34` |
| `User(...)` + `room.add_user` | `app/ws/router.py:36-37` |
| Ответ `connect{id}` | `app/ws/router.py:39` |
| Цикл `receive_json` → `handler.handle` | `app/ws/router.py:41-44` |
| `WebSocketDisconnect` (норма) | `app/ws/router.py:45-46` |
| Прочие ошибки → close `1011` | `app/ws/router.py:47-53` |
| `finally: room.remove_user` | `app/ws/router.py:54-55` |
| `ConnectMessage(type=Literal["connect"], name)` | `app/ws/schemas.py:6-10` |

### 7.2. Диспетчер входящих (`app/modules/room/handler.py`)

```python
_VALID_ACTIONS = frozenset({"play", "pause", "status", "load", "set_video", "info"})  # handler.py:10
```

`UserHandler.handle` (`handler.py:20-45`):

1. `action = data.get("type")`; если `action not in _VALID_ACTIONS` → **`return` (молчаливое игнорирование)** — `handler.py:21-23`. Так отбрасываются `connect`, `seek`, `remove_block_pause` и любой мусор.
2. `info` → `user.info = {…без "type"}`, выход — `handler.py:27-29`.
3. `set_video` → `_handle_set_video`, выход (до обновления времени) — `handler.py:31-33`.
4. Иначе обновляются `user.current_time` / `user.downloaded_time` — `handler.py:35-36`.
5. Дальше — `status`/`play`/`pause`/`load` → одноимённый `_handle_*` — `handler.py:38-45`.

| Входящий тип | Обработчик | Что делает |
|---|---|---|
| `info` | inline, `handler.py:27-29` | Складывает метаданные в `user.info`. |
| `status` | `_handle_status`, `handler.py:47-59` | `check_is_loaded` → `play`/`remove_block_pause`; ретрансляция как `info` (минус `current_time`, плюс `name`) — `handler.py:56-59`. |
| `play` | `_handle_play`, `handler.py:61-67` | `seek`(исключая себя) → `load` → `is_paused=False` → если готовы все `play`. |
| `pause` | `_handle_pause`, `handler.py:69-76` | `seek`(исключая себя) → `pause`(исключая себя) → `load` → `is_paused=True`. |
| `load` | `_handle_load`, `handler.py:78-86` | `load`; если готовы все → `remove_block_pause` (если `is_paused`) или `play`. |
| `set_video` | `_handle_set_video`, `handler.py:88-95` | Валидирует `video_url`/`url`; `set_video_broadcast`. Без валидного URL — `warning` и выход (`handler.py:91-93`). |

`_broadcast` (`handler.py:16-18`) рассылает всем, кроме отправителя (`room.get_users_exc(self.user)`).

### 7.3. Исходящие `send_json` (`app/modules/room/models.py`)

| Тип (s→c) | Функция | Кому | Кадр |
|---|---|---|---|
| `seek` | `Room.seek`, `models.py:94-105` | всем, кроме `exception_user`, либо одному `user` | `{"type":"seek","current_time": …}` |
| `seek` (коррекция) | `Room.check_is_loaded`, `models.py:71-75` | каждому отстающему | `{"type":"seek","current_time": room.current_time}` |
| `play` | `Room.play`, `models.py:85-87` | **всем** (`user_storage`) | `{"type":"play"}` |
| `pause` | `Room.pause`, `models.py:89-92` | всем, кроме `exception_user` | `{"type":"pause"}` |
| `set_video` | `Room.set_video_broadcast`, `models.py:107-116` | **всем** | `{"type":"set_video","video_url": …,"current_time": …}` |
| `remove_block_pause` | `Room.remove_block_pause`, `models.py:118-119` | **всем** | `{"type":"remove_block_pause"}` |
| `info` (ретрансляция `status`) | `_broadcast` из `_handle_status`, `handler.py:56-59` | всем, кроме отправителя | `{"type":"info","name": …, "downloaded_time": …}` |
| `connect` | `app/ws/router.py:39` | подключившемуся | `{"type":"connect","id": …}` |

Готовность: `Room.check_is_loaded` (`models.py:67-83`), порог `settings.REQUIRED_DOWNLOAD_TIME` (`models.py:78`), значение по умолчанию `15` — `app/config.py:17`. `REQUIRED_DOWNLOAD_TIME` переопределяется одноимённой переменной окружения (имя переменной — `REQUIRED_DOWNLOAD_TIME`; содержимое `.env` здесь не приводится).

### 7.4. Конкурентность

`Room._lock: asyncio.Lock` (`models.py:43`) сериализует `add_user` (`45-47`), `remove_user` (`49-52`) и `check_is_loaded` (`67-83`). Не вызывайте `play()`/`pause()`/`seek()` **изнутри** удерживаемого лока — выходите из него перед рассылкой (см. `Sync-Mate-API-WS/CLAUDE.md`).

### 7.5. Контекст развёртывания (актуально)

Для протокола несущественно, но во избежание дрейфа: `docker-compose.yml` содержит **единственный** сервис `sync-mate-api-ws` (сервис `cloudflared` удалён в коммите `f0c7443`). CI (`.github/workflows/ci.yml`) гоняет линт/типы/тесты только на **Python 3.13**. Подробности — в `docs/deployment.md`.

---

## См. также

- [`docs/architecture.md`](architecture.md) — слоистая модель, потоки REST/WS, доменная модель комнаты.
- [`docs/rest-api.md`](rest-api.md) — REST CRUD комнат и Rezka-эндпоинты (создание комнаты, redirect).
- [`docs/configuration.md`](configuration.md) — `Settings`, переменные окружения (включая `REQUIRED_DOWNLOAD_TIME`).
- [`docs/deployment.md`](deployment.md) — Docker, CI/CD, актуальный состав сервисов.
- [`docs/testing.md`](testing.md) · [`docs/conventions.md`](conventions.md) · [`docs/rezka.md`](rezka.md).
- Зеркало с перспективой фронта: `../../Sync-Mate-Extension/docs/websocket-protocol.md`.
- Гиды: [`../CLAUDE.md`](../CLAUDE.md) (бэкенд) · [корневой `CLAUDE.md`](../../CLAUDE.md).
