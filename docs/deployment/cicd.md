# CI/CD

Минимальный CI/CD для cookies-контура реализован в `.github/workflows/build-cookies.yml`.

## Триггеры

- `push` в ветку `cookies` (только при изменениях в cookies-контуре).
- `workflow_dispatch` с параметром `deploy_to_server`.

## Что делает workflow

1. Собирает и публикует в GHCR образ `cookies-extractor` с тегами:
   - `cookies`
   - `cookies-sha-<commit>`
2. Собирает и публикует в GHCR образ `cookies-session-refresher` с тегами:
   - `cookies-refresh`
   - `cookies-refresh-sha-<commit>`
3. Автоматически копирует на сервер runtime-файлы в `~/cookies/runtime`:
   - `compose.cookies.yml`
   - `compose.cookies-refresh.yml`
   - `run_cookies_extractor.sh`
   - `run_session_refresher.sh`
   - `run_refresh_then_extract.sh`
   - `prepare_firefox_profile.sh`
   - `cookies.cron.example`
4. Делает `docker pull` обоих образов и валидирует compose-конфиги.

Контур полностью автономен и не использует `~/bot-prod` или `~/bot-dev`.

## Секреты workflow

- `SSH_HOST`
- `SSH_USER`
- `SSH_PRIVATE_KEY`
- `GHCR_PAT` (рекомендуется PAT classic с `read:packages` и `repo` для приватного репозитория)
- `GHCR_USERNAME` (GitHub-логин владельца PAT, опционально; если не задан, используется owner репозитория)
