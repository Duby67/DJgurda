# DJgurda Telegram Bot

Этот репозиторий подготавливает базу для Telegram-бота на Python.

## С чего начать

1. Создано виртуальное окружение `venv` на базе:
`C:\Users\Duby6\AppData\Local\Programs\Python\Python311\python.exe`
2. В VSCode настроена автоактивация окружения через:
`${workspaceFolder}\venv\Scripts\activate.bat`
3. Зависимости описаны в `requirements.txt`.

## Документы и структура

- `README.md` - первичное знакомство (этот файл).
- `ARCHITECTURE.md` - короткая карта структуры проекта.
- `AGENTS.md` - правила и контекст для агентной работы.
- `docs/` - дополнительная документация.
- `docs/deployment/` - политика веток, CI/CD, cron и cookies-контур.
- `docs/deployment/cookies-host-setup.md` - подготовка Ubuntu-хоста под cookies-контур.
- `docs/deployment/session-refresh-manual.md` - ручной сценарий восстановления Firefox-профиля и запуска автообновления сессии.
- `deploy/` - каркас docker/compose/cron для запуска контуров.
- `src/` - исходный код проекта.
- `src/cookies_extractor/` - контур извлечения cookies в `cookies.txt`.
- `src/session_refresher/` - контур обновления Firefox-сессии перед извлечением cookies.

## Быстрый запуск (локально)

```bat
venv\Scripts\activate.bat
pip install -r requirements.txt
```
