# Документация — Sync-Mate-API-WS

Подробный справочник по бэкенду (FastAPI + WebSocket-сервер для синхронного просмотра на Rezka).
Это источник правды по коду этого репозитория. Тонкие правила для Claude — в [../CLAUDE.md](../CLAUDE.md);
система контроля и процесс — в `.claude/docs/` корня workspace (или `/playbook`).

## Содержание

| Документ | О чём |
|---|---|
| [architecture.md](architecture.md) | Слоистая модель, фабрика приложения, потоки REST/WS, доменная модель `Room`/`User`, правила `asyncio.Lock`, DI, enforced-правила |
| [websocket-protocol.md](websocket-protocol.md) | **Контракт WS-протокола** (общий с расширением): рукопожатие, коды закрытия, все 9 типов сообщений, алгоритм синхронизации |
| [rest-api.md](rest-api.md) | Все REST-эндпоинты: `/api/info`, комнаты (CRUD + redirect), Rezka (поиск/инфо/источники) |
| [rezka.md](rezka.md) | Интеграция с rezka.ag: `RezkaService`/`RezkaStream`, декодирование URL потока, прокси, хрупкие места |
| [configuration.md](configuration.md) | `Settings`, переменные окружения (только имена), запуск, Makefile |
| [testing.md](testing.md) | pytest-конвенции, фикстуры, паттерны моков, запуск через гейт |
| [deployment.md](deployment.md) | Docker, `docker-compose`, CI (`ci.yml`), CD по тегу (`cd.yml`), GHCR, сервер |
| [conventions.md](conventions.md) | Стиль кода, конфиги линтеров, «Что НЕ делать» с обоснованием |
| [adr/](adr/) | Architecture Decision Records — зафиксированные ключевые решения и их причины |

## Как это поддерживается в синхроне

Документация — часть контракта, а не «приписка». Правило:

- Любое изменение поведения/архитектуры/контракта **обновляет соответствующий документ в этом `docs/`** в том же изменении (этим занимается агент `docs-sync`, шаг в скиле `/finish`).
- **WS-протокол** ([websocket-protocol.md](websocket-protocol.md)) — общий с расширением. Любая правка типа сообщения затрагивает обе стороны и оба `websocket-protocol.md`; парность кода проверяет `python scripts/protocol_sync.py` (гейт-проверка `protocol`), а скил `/sync-protocol` + агент `protocol-guardian` следят за обеими сторонами.
- Значимые решения фиксируются как ADR в [adr/](adr/) (не переписывай старые — добавляй новые со статусом «Supersedes …»).

## См. также

- [../CLAUDE.md](../CLAUDE.md) — краткие правила по бэкенду
- [../../CLAUDE.md](../../CLAUDE.md) — общий гид workspace и система контроля
- [../../Sync-Mate-Extension/docs/](../../Sync-Mate-Extension/docs/) — документация расширения (вторая сторона WS-контракта)
