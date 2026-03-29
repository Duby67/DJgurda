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
- `docs/deployment/` - политика веток, CI/CD, cron и cookies.
- `deploy/` - каркас docker/compose/cron для запуска контуров.
- `src/` - исходный код проекта.
- `src/cookies_extractor/` - контур для извлечения cookies YouTube.

## Быстрый запуск (локально)

```bat
venv\Scripts\activate.bat
pip install -r requirements.txt
```
