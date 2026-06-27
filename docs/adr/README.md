# Architecture Decision Records — Sync-Mate-API-WS

Короткие записи значимых решений: **контекст → решение → последствия**. ADR неизменяемы —
если решение меняется, добавляй новый ADR со статусом `Supersedes ADR-NNNN`, а у старого ставь
`Superseded by ADR-MMMM`. Это объясняет «почему так», чтобы будущие сессии не «чинили то, что не сломано».

| ADR | Решение | Статус |
|---|---|---|
| [0001](0001-in-memory-rooms.md) | Комнаты хранятся в памяти, без персистентности | Accepted |
| [0002](0002-async-only-rezka.md) | Все вызовы Rezka — async (`httpx.AsyncClient`) | Accepted |
| [0003](0003-ws-protocol-shared-contract.md) | WS-протокол — общий контракт BE↔FE | Accepted |
| [0004](0004-tag-equals-deploy.md) | Тег `v*` = деплой, push = только CI | Accepted |

Шаблон нового ADR — [0000-template.md](0000-template.md).
