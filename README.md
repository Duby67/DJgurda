# DJgurda Telegram Bot

Репозиторий содержит Telegram-бота на Python и отдельный
cookies-контур для автообновления Firefox-сессии.

## С чего начать

1. Создано виртуальное окружение `venv` на базе:
`C:\Users\Duby6\AppData\Local\Programs\Python\Python311\python.exe`
2. В VSCode настроена автоактивация окружения через:
`${workspaceFolder}\venv\Scripts\activate.bat`
3. Зависимости бота описаны в `requirements.txt`.
4. Зависимости cookies-refresher образа вынесены в
`requirements-cookies.txt`.

## Документы и структура

- `README.md` - первичное знакомство (этот файл).
- `ARCHITECTURE.md` - короткая карта структуры проекта.
- `AGENTS.md` - правила и контекст для агентной работы.
- `docs/` - дополнительная документация.
- `docs/deployment/` - политика веток, CI/CD, cron и cookies-контур.
- `docs/deployment/cookies-host-setup.md` - подготовка Ubuntu-хоста под session-refresher.
- `docs/deployment/session-refresh-manual.md` - ручной сценарий подготовки
  Firefox-профилей и запуска session-refresher.
- `deploy/` - docker/compose/cron обвязка контуров.
- `test/docker/` - локальные стенды для проверки Docker-образов
  без ожидания выгрузки на сервер.
- `src/` - исходный код проекта.
- `src/session_refresher/` - контейнерный Selenium-раннер обновления Firefox-сессии.

## Быстрый запуск бота локально

```bat
venv\Scripts\activate.bat
pip install -r requirements.txt
```
