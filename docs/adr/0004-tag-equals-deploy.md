# ADR-0004: Тег `v*` = деплой в прод, push = только CI

- **Статус:** Accepted
- **Дата:** 2026-06-27

## Контекст

Нужна простая, но контролируемая модель выката без веток/PR-церемоний. GitHub Actions уже разделяют
два события: push прогоняет проверки, тег запускает выкат.

## Решение

- **push** в `main`/`master` → `ci.yml` (lint-format / type-check / security / test, Python 3.13). Деплоя нет.
- **тег `v*`** → `cd.yml`: сборка образа в GHCR (`ghcr.io/zebaro24/sync-mate-api-ws`, версия из тега + `:latest`)
  и деплой по SSH на сервер (`docker compose up -d --pull always`, прод `https://sync-mate-api-ws.zebaro.dev`).

См. [../deployment.md](../deployment.md).

## Последствия

- ➕ Выкат — осознанное действие (тег), а не побочный эффект push.
- 🔒 В системе контроля Claude это усилено: `git push` гейтится (`/approve-push`), а теги ставятся
  только через скил `/release` (strict-гейт + bump версии + CHANGELOG + подтверждение). Хук `guard-git`
  блокирует ad-hoc теги и негейтнутый push.
- ➖ Прод тянет `:latest` через `--pull always`; версия-тег пушится в GHCR, но потребляется `:latest`.
