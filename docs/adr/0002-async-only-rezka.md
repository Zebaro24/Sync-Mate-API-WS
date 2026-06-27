# ADR-0002: Все вызовы Rezka — async (`httpx.AsyncClient`)

- **Статус:** Accepted
- **Дата:** 2026-06-27 (зафиксировано постфактум)

## Контекст

Сервис на FastAPI/uvicorn полностью асинхронный. Обращения к rezka.ag — сетевой I/O. Синхронный
HTTP-клиент (`requests` или `httpx.Client`) внутри `async def` блокирует event loop и убивает
конкурентность WS-соединений.

## Решение

Все методы `RezkaService`/`RezkaStream` — `async`, поверх `httpx.AsyncClient`; роутеры обязаны их
`await`. Синхронный HTTP в `app/` запрещён. См. [../rezka.md](../rezka.md).

## Последствия

- ➕ Event loop не блокируется; ротация прокси и параллельные запросы работают корректно.
- ➖ Любой новый код к Rezka обязан быть async — нельзя «по-быстрому» вернуть sync.
- 🔒 Enforced: `scripts/arch_lint_api.py` запрещает `import requests` и `httpx.Client(` в `app/`
  (гейт-проверка `arch`). Нарушение валит гейт.
