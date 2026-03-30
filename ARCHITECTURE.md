# Архитектура репозитория

Короткая карта текущей структуры:

- `.vscode/` - локальные настройки VSCode (включая автоактивацию `venv`).
- `venv/` - виртуальное окружение Python 3.11.
- `docs/` - дополнительная проектная документация.
- `docs/deployment/` - правила веток, CI/CD, cron и политика cookies-контура.
- `deploy/` - инфраструктурный каркас (docker/compose/cron).
- `deploy/docker/bot-prod/` - Docker-контур production.
- `deploy/docker/bot-dev/` - Docker-контур dev.
- `deploy/docker/bot-local/` - Docker-контур локального запуска.
- `deploy/docker/cookies-session-refresher/` - Docker-контур автообновления Firefox-сессии.
- `deploy/compose/` - шаблоны compose для `prod/dev/local/cookies`.
- `deploy/cron/` - runtime-скрипты для session-refresher.
- `src/` - исходный код проекта.
- `src/session_refresher/` - рабочий контур автообновления Firefox-сессии.
- `.github/workflows/` - CI/CD workflow-файлы.
- `requirements.txt` - зависимости Python-проекта.
- `requirements-dev.txt` - зависимости разработки и тестирования.

Политика контуров:
- `prod`, `dev` - только автодеплой.
- `cookies` - только автодеплой (серверный запуск session-refresher).
- `local` - только локальный запуск.
