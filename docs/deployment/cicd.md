# CI/CD

CI/CD для cookies-контура реализован в
`.github/workflows/build-cookies.yml`.

## Триггеры

- `push` в ветку `cookies`.
  Запуск только при изменениях в session-refresher контуре.
- `workflow_dispatch` с параметром `deploy_to_server`.

## Что делает workflow

1. Собирает и публикует в GHCR образ `cookies-session-refresher`.
   Теги:
   - `cookies-refresh`
   - `cookies-refresh-sha-<commit>`
2. Копирует runtime-файлы в `~/cookies/runtime`:
   - `compose.cookies-refresh.yml`
   - `run_session_refresher.sh`
   - `prepare_firefox_profile.sh`
   - `refresh_sources.list`
   - `cookies.cron.example`
3. Создает недостающие директории:
   - `~/cookies/runtime`
   - `~/firefox_selenium_profile`
   - `~/logs`
4. Делает `docker pull` образа `cookies-refresh`.
5. Валидирует compose-конфигурацию.

CI/CD не создает `~/cookies/<source>`.
Эти папки создает `run_session_refresher.sh` по `refresh_sources.list`.

CI/CD не вносит изменения в `crontab` автоматически.

## Секреты workflow

- `SSH_HOST`
- `SSH_USER`
- `SSH_PRIVATE_KEY`
- `GHCR_PAT`
  Рекомендуется PAT classic с `read:packages` и `repo`
  для приватного репозитория.
- `GHCR_USERNAME`
  GitHub-логин владельца PAT. Опционально: если не задан,
  используется owner репозитория.
