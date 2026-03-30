# CI/CD

CI/CD для cookies-контура реализован в `.github/workflows/build-cookies.yml`.

## Триггеры

- `push` в ветку `cookies` (только при изменениях в session-refresher контуре).
- `workflow_dispatch` с параметром `deploy_to_server`.

## Что делает workflow

1. Собирает и публикует в GHCR образ `cookies-session-refresher` с тегами:
   - `cookies-refresh`
   - `cookies-refresh-sha-<commit>`
2. Автоматически копирует на сервер runtime-файлы в `~/cookies/runtime`:
   - `compose.cookies-refresh.yml`
   - `run_session_refresher.sh`
   - `prepare_firefox_profile.sh`
   - `cookies.cron.example`
3. Создает недостающие директории на сервере:
   - `~/cookies/runtime`
   - `~/firefox_profile`
   - `~/logs`
4. Делает `docker pull` образа `cookies-refresh` и валидирует compose-конфигурацию.

CI/CD не вносит изменения в `crontab` автоматически.

## Секреты workflow

- `SSH_HOST`
- `SSH_USER`
- `SSH_PRIVATE_KEY`
- `GHCR_PAT` (рекомендуется PAT classic с `read:packages` и `repo` для приватного репозитория)
- `GHCR_USERNAME` (GitHub-логин владельца PAT, опционально; если не задан, используется owner репозитория)
