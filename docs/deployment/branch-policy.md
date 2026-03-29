# Политика веток, образов и тегов

## Контуры

- `prod` - только автодеплой.
- `dev` - только автодеплой.
- `cookies` - автодеплой и локальный запуск.
- `local` - только локальный запуск.

## Именование образов

Рекомендуемый шаблон имени: `djgurda/<service>:<tag>`.

Примеры:
- `djgurda/bot-prod:prod`
- `djgurda/bot-dev:dev`
- `djgurda/bot-local:local`
- `djgurda/cookies-extractor:cookies`

## Правила запуска по веткам

- `main` -> пересборка и выкладка `bot-prod`.
- `dev` -> пересборка и выкладка `bot-dev`.
- ветка/джоба `cookies` -> пересборка `cookies-extractor`.
- `local` контур в CI не деплоится на сервер.
