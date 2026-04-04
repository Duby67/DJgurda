# Архитектура репозитория

Короткая карта текущей структуры:

- `.vscode/` - локальные настройки VSCode (включая
  автоактивацию `venv`).
- `venv/` - виртуальное окружение Python 3.11.
- `docs/` - дополнительная проектная документация.
- `docs/deployment/` - правила веток, CI/CD, cron и
  политика cookies-контура.
- `deploy/` - инфраструктурный каркас (docker/compose/cron).
- `deploy/docker/bot-prod/` - Docker-контур production.
- `deploy/docker/bot-dev/` - Docker-контур dev.
- `deploy/docker/bot-local/` - Docker-контур локального запуска.
- `deploy/docker/cookies-session-refresher/` - Docker-контур
  автообновления Firefox-сессии.
- `deploy/compose/` - compose-шаблоны для
  `prod/dev/local/cookies`.
- `deploy/cron/` - runtime-скрипты cookies-контура:
  `run_session_refresher.sh`, `prepare_firefox_profile.sh`,
  `refresh_sources.list`.
- `src/` - исходный код проекта.
- `src/session_refresher/` - контейнерный Selenium
  runtime-wrapper и Python-раннер.
- `.github/workflows/` - CI/CD workflow-файлы.
- `requirements.txt` - зависимости Python-проекта.
- `requirements-dev.txt` - зависимости разработки и
  тестирования.
- `requirements-cookies.txt` - зависимости cookies
  session-refresher образа.

Политика контуров:

- `prod`, `dev` - только автодеплой.
- `cookies` - только автодеплой runtime-файлов и образа
  session-refresher; запуск ручной или через cron на сервере.
- `local` - только локальный запуск.
