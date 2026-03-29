# CI/CD

Минимальный CI/CD для cookies-extractor реализован в `.github/workflows/build-cookies.yml`.

## Триггеры

- `push` в ветку `cookies` (только при изменениях в cookies-контуре).
- `workflow_dispatch` с параметром `deploy_to_server`.

## Что делает workflow

1. Собирает образ `cookies-extractor` из `deploy/docker/cookies-extractor/Dockerfile`.
2. Публикует его в GHCR с тегами:
   - `cookies` (стабильный тег для cron-запусков).
   - `sha-<commit>` (аудит и откат).
3. Автоматически копирует на сервер необходимые runtime-файлы:
   - `deploy/compose/compose.cookies.yml`
   - `deploy/cron/run_cookies_extractor.sh`
4. Размещает их в `~/cookies/runtime`, подтягивает свежий образ (`docker pull`) и валидирует compose-конфигурацию.

Контур cookies-extractor полностью автономен и не использует `~/bot-prod` или `~/bot-dev`.
Контейнер не запускается постоянно: запуск по расписанию выполняет `cron`.

## Секреты workflow

- `SSH_HOST`
- `SSH_USER`
- `SSH_PRIVATE_KEY`
- `GHCR_PAT` (минимум `read:packages` для сервера)
