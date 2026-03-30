# Политика веток, образов и тегов

## Контуры

- `prod` - только автодеплой.
- `dev` - только автодеплой.
- `cookies` - только автодеплой (серверный запуск session-refresher).
- `local` - только локальный запуск.

## Именование образов

Для текущего GHCR-потока используются теги в образе репозитория `ghcr.io/<owner>/<repo>`.

Примеры:
- `ghcr.io/duby67/djgurda:prod`
- `ghcr.io/duby67/djgurda:dev`
- `ghcr.io/duby67/djgurda:cookies-refresh` (session-refresher)

## Правила запуска по веткам

- `main` -> пересборка и выкладка `bot-prod`.
- `dev` -> пересборка и выкладка `bot-dev`.
- ветка/джоба `cookies` -> пересборка и выкладка образа `cookies-refresh`.
- `local` контур в CI не деплоится на сервер.
