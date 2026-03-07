# DJgurda Bot

Асинхронный Telegram-бот для обработки медиа-ссылок в чатах.  
Текущий рабочий контур поддерживает:
- TikTok (`video`, `profile`, `media_group`)
- YouTube (`shorts`, `channel`)
- Instagram (`reels`, `media_group`, `stories`, `profile`)

Бот сохраняет статистику по чатам и пользователям.

## Продуктовое допущение (mobile-first)

- Основной сценарий использования бота и просмотра полученного контента - мобильный клиент Telegram на телефонах.
- При проектировании форматов ответов, подписей и медиа-групп приоритет отдается удобству чтения и просмотра на экранах смартфонов.

## Главный контекст проекта

Основной источник контекста для разработчиков и AI-агентов:

- [`.github/ai_context.md`](./.github/ai_context.md)
- [`IMPROVEMENTS.md`](./IMPROVEMENTS.md)

Политика актуальности:

- `README.md` и `.github/ai_context.md` - канонические документы.
- Контекст всегда проверяется по коду в `src/`.
- При любом обращении к `README.md` агент обязан дополнительно проверить `.github/ai_context.md` и `IMPROVEMENTS.md`.
- В пользовательских caption хэштеги из заголовков контента должны удаляться; если заголовок после очистки пустой, используется нейтральный fallback-текст.

## Важный статус по структуре

- `docs/` не используется как поддерживаемый источник актуального контекста.
- `tests/` / `test/` на текущем этапе в основном считаются legacy-зоной и не являются источником истины.
- Исключение: для локальной проверки handlers используй smoke-скрипты:
  - `test/TikTok/test_tiktok_handlers_local.py` + `test/TikTok/TikTok_urls.py`
  - `test/YouTube/test_youtube_handlers_local.py` + `test/YouTube/urls.py`
  - `test/Instagram/test_instagram_handlers_local.py` + `test/Instagram/urls.py`
- При возврате к этим областям в будущем их нужно явно заново договорить и обновить в `.github/ai_context.md`.

## Быстрый запуск

1. Требования:
   - Python 3.11+
   - FFmpeg в `PATH`
2. Установка:

   ```bash
   python -m venv venv
   # Windows PowerShell
   .\venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   # при необходимости dev-инструментов:
   # python -m pip install -r requirements-dev.txt
   ```

3. Настройка `.env` (обязательные переменные валидируются в `src/config.py`):
   - `BOT_DB_PATH`
   - `BOT_VERSION`
   - `ADMIN_ID`
   - `BOT_TOKEN`
   - `YANDEX_MUSIC_TOKEN`
   - `YOUTUBE_COOKIES_PATH`

   Шаблон:
   - `env.example` (скопируй в `.env` и подставь значения).
   - Для локальных проверок и тестовых сценариев ориентируйся на `env.example` как на эталонный набор переменных.
   - Персональный файл `local/.env` не является частью проекта и не должен использоваться как источник проектного контекста.

   Для Docker/deploy используются значения путей внутри контейнера:
   - `BOT_DB_PATH=/app/src/data/db/bot.db`
   - `YOUTUBE_COOKIES_PATH=/app/src/data/cookies/youtube_cookies.txt`
4. Старт:

   ```bash
   python -m src.main
   ```

## Локальная среда и прод

- Локальная среда разработки: Windows 11.
- Целевая среда запуска бота: Ubuntu 24 (Docker/сервер).
- Из-за различий ОС (пути, shell-команды, бинарники вроде `ffmpeg`) часть локальных сценариев на Windows может отличаться от поведения в Ubuntu.

## Точки входа и ключевые файлы

- `src/main.py` - старт приложения.
- `src/config.py` - env-конфигурация и лимиты.
- `src/bot/processing/media_router.py` - вход в поток обработки ссылок.
- `src/handlers/manager.py` - выбор обработчика по URL.
- `src/middlewares/db/*` - модели и DB-операции.
- `.github/workflows/*` и `manager.sh` - CI/CD и деплой.

## Команды бота

- `/help` - список активных источников.
- `/info` - версия и время запуска бота.
- `/statistics` - статистика активности чата за все время:
  - в начале показывается самый часто отправляемый ресурс по чату;
  - далее выводится топ пользователей (лимит задается в `STATISTICS_TOP_USERS_LIMIT`, сейчас `3`);
  - имена пользователей выводятся ссылками на Telegram-аккаунты.
- `/start`, `/stop`, `/toggle_bot` - управление включением бота в текущем чате.
- `/toggle_errors` - включение/выключение сообщений об ошибках источников.
- `/toggle_notifications` - включение/выключение уведомлений о старте/остановке бота.

## Схема расположения файлов (сервер и контейнер)

Подробная схема вынесена в отдельный файл:

- [`DEPLOY_LAYOUT.md`](./DEPLOY_LAYOUT.md)

## Release Notes

- [`RELEASE_NOTES.md`](./RELEASE_NOTES.md)

## Релизная синхронизация версии

- Источник версии в коде: `src/__init__.py` (`__version__`).
- Для релиза в `prod` рекомендуется ставить tag на тот же commit (например, `v1.2.0`).
- Скрипт проверки/подготовки релиза:
  - проверяет соответствие `__version__` и tag;
  - проверяет наличие секции в `RELEASE_NOTES.md`;
  - проверяет/обновляет метку ревизии backlog в `IMPROVEMENTS.md`.

Проверка (без изменений файлов):

```bash
python scripts/release_sync.py --tag v1.2.0
```

Автодобавление шаблона в `RELEASE_NOTES.md` и обновление ревизии в `IMPROVEMENTS.md`:

```bash
python scripts/release_sync.py --tag v1.2.0 --write
```

## Процедура выпуска версии

1. Убедиться, что все текущие изменения закоммичены.
2. Убедиться, что актуальная ветка `dev` запушена в `origin/dev`.
3. Перейти в `main` и выполнить merge `dev`.
4. Повысить версию в `src/__init__.py` по схеме `major.minor.patch` (каждое число 0..9):
   - если `patch < 9`: увеличить `patch`;
   - если `patch == 9`: `patch = 0`, увеличить `minor`;
   - если при переносе `minor == 9`: `minor = 0`, увеличить `major`.
5. Создать новый tag `vX.Y.Z` и проверить соответствие `__version__ == X.Y.Z`.
6. Обновить `RELEASE_NOTES.md` на основе выполненных задач.
7. Удалить выполненные задачи из активного backlog `IMPROVEMENTS.md`.
8. После этого выполнить финальный commit/push.

## Текущее ограничение

В runtime зарегистрированы `TikTokHandler`, `YouTubeHandler`, `InstagramHandler`.  
`YandexMusic` и `VK` handlers присутствуют в коде, но пока не подключены в `ServiceManager`.

## База данных

- Инициализация выполняется через SQLAlchemy (`Base.metadata.create_all`).
- Исторический модуль миграции удален из runtime-цепочки: проект ожидает актуальную схему БД.
- Основные таблицы: `bot_settings`, `sources`, `stats`.

## Деплой

- Серверный скрипт деплоя: `manager.sh`.
- Запуск: `./manager.sh dev` или `./manager.sh prod`.
- Скрипт ожидает env-файл на сервере по пути `$HOME/bot_{env}/.env` и валидирует обязательные ключи перед запуском контейнера.
- `manager.sh` общий для `dev` и `prod`: любые правки должны сохранять совместимость перезапуска обоих окружений.
- Учитывай, что `prod` может временно отставать от `dev`, поэтому нельзя делать изменения, работающие только для одного окружения.

## Управление в чатах

- Команды `/start` и `/stop` разрешены для всех участников чата.
- Эти команды влияют только на флаг работы бота в текущем чате и не затрагивают другие чаты.
- Когда бот выключен в чате, он не обрабатывает другие сообщения и команды, кроме `/start`, `/stop`, `/toggle_bot`.
