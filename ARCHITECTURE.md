# Архитектура репозитория

Короткая карта текущей структуры:

- `.vscode/` - локальные настройки VSCode (включая автоактивацию `venv`).
- `venv/` - виртуальное окружение Python 3.11.
- `docs/` - дополнительная проектная документация.
- `docs/deployment/` - правила веток, CI/CD, cron и политика cookies.
- `deploy/` - инфраструктурный каркас (docker/compose/cron).
- `deploy/docker/` - 4 docker-контура:
  - `bot-prod`
  - `bot-dev`
  - `bot-local`
  - `cookies-extractor`
- `deploy/compose/` - шаблоны compose для `prod/dev/local/cookies`.
- `deploy/cron/` - шаблон cron-задачи для cookies-extractor.
- `.github/workflows/` - CI/CD workflow-файлы (папка подготовлена).
- `requirements.txt` - зависимости Python-проекта.
- `requirements-dev.txt` - зависимости разработки и тестирования.
- `README.md` - документ для первичного ознакомления.
- `AGENTS.md` - агентно-ориентированный контекст работы.

Политика контуров:
- `prod`, `dev` - только автодеплой.
- `cookies` - автодеплой и локальный запуск.
- `local` - только локальный запуск.
