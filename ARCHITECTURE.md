# Архитектура репозитория

Короткая карта текущей структуры:

- `.vscode/` - локальные настройки VSCode (включая автоактивацию `venv`).
- `venv/` - виртуальное окружение Python 3.11.
- `docs/` - дополнительная проектная документация.
- `docs/deployment/` - правила веток, CI/CD, cron и политика cookies.
- `deploy/` - инфраструктурный каркас (docker/compose/cron).
- `deploy/docker/bot-prod/` - Docker-контур production.
- `deploy/docker/bot-dev/` - Docker-контур dev.
- `deploy/docker/bot-local/` - Docker-контур локального запуска.
- `deploy/docker/cookies-extractor/` - Docker-контур экстрактора cookies.
- `deploy/compose/` - шаблоны compose для `prod/dev/local/cookies`.
- `deploy/cron/` - шаблон cron-задачи для cookies-extractor.
- `src/` - исходный код проекта.
- `src/cookies_extractor/` - рабочий контур скриптов извлечения cookies.
- `.github/workflows/` - CI/CD workflow-файлы.
- `requirements.txt` - зависимости Python-проекта.
- `requirements-dev.txt` - зависимости разработки и тестирования.

Политика контуров:
- `prod`, `dev` - только автодеплой.
- `cookies` - только автодеплой (серверный запуск).
- `local` - только локальный запуск.
