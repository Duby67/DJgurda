# DJgurda Bot

Асинхронный Telegram-бот для обработки медиа-ссылок в чатах.  
Текущий рабочий контур поддерживает:

- TikTok (`video`, `profile`, `media_group`)
- YouTube (`shorts`, `channel`)
- Instagram (`reels`, `media_group`, `stories`, `profile`)
- COUB (`video`)
- VK Music (`audio`, `playlist`)

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
- `test/` Содержит скрипты для локальной проверки.
  - `test/handlers/` smoke-скрипты для локальной проверки handlers.
  - Все тесты (`pytest` и smoke-скрипты) запускать только с повышенными правами после явного подтверждения пользователя.

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

   Важно:
   - Зависимости проекта устанавливаются в проектный `venv`, а не в системный Python.
   - Для локальных запусков и проверок используй активированный `venv` или явный путь `.\venv\Scripts\python.exe`.

3. Настройка `.env` (обязательные переменные валидируются в `src/config.py`):
   - `BOT_DB_PATH`
   - `BOT_VERSION`
   - `ADMIN_ID`
   - `BOT_TOKEN`
   - `YANDEX_MUSIC_TOKEN`

   Опционально для временных файлов:
   - `BOT_TEMP_DIR` (опционально; если не задан, используется системный temp-dir, например `/tmp/djgurda/temp_files` в Docker)

   Общая директория cookies (рекомендуемый режим):
   - `COOKIES_DIR` (опционально; по умолчанию `src/data/cookies`)
   - Если `*_COOKIES_PATH` не задан, обработчик автоматически ищет cookies в `COOKIES_DIR`:
     - `youtube_cookies.txt`
     - `instagram_cookies.txt`
     - `vk.com_cookies.txt`

   Опционально для YouTube cookies:
   - `YOUTUBE_COOKIES_ENABLED` (`true/false`, по умолчанию `true`)
   - `YOUTUBE_COOKIES_PATH` (опционально; явный override, иначе используется `COOKIES_DIR/youtube_cookies.txt`)

   Важное замечание:
   - Если `youtube_cookies.txt` является заглушкой (пустой или без валидных cookie-строк), YouTube handler автоматически игнорирует этот файл.
   - По умолчанию handler пытается использовать валидный cookies-файл (если он доступен).
   - Для принудительного отключения cookies установи `YOUTUBE_COOKIES_ENABLED=false`.

   Опционально для Instagram cookies:
   - `INSTAGRAM_COOKIES_ENABLED` (`true/false`, по умолчанию `true`)
   - `INSTAGRAM_COOKIES_PATH` (опционально; явный override, иначе используется `COOKIES_DIR/instagram_cookies.txt`)

   Важное замечание:
   - Для части Instagram Stories требуется авторизация; без валидных Instagram cookies возможна ошибка доступа (`You need to log in to access this content`).

   Опционально для VK cookies:
   - `VK_COOKIES_ENABLED` (`true/false`, по умолчанию `true`)
   - `VK_COOKIES_PATH` (опционально; явный override, иначе используется `COOKIES_DIR/vk.com_cookies.txt`)
   - Рекомендуемый локальный путь: `src/data/cookies/vk.com_cookies.txt`
   - Историческое имя `vk_cookies.txt` больше не используется

   Важное замечание:
   - Для части VK Music ссылок требуется авторизованная сессия; без валидных VK cookies обработчик может не извлечь audio URL/playlist metadata.
   - Если `vk.com_cookies.txt` пустой или выглядит как заглушка, VK handler автоматически игнорирует его.

   Шаблон:
   - `env.example` (скопируй в `.env` и подставь значения).
   - Для локальных проверок и тестовых сценариев ориентируйся на `env.example` как на эталонный набор переменных.
   - Персональный файл `local/.env` не является частью проекта и не должен использоваться как источник проектного контекста.

   Для Docker/deploy используются значения путей внутри контейнера:
   - `BOT_DB_PATH=/app/src/data/db/bot.db`
   - `COOKIES_DIR=/app/src/data/cookies`
   - `BOT_TEMP_DIR=/tmp/djgurda/temp_files`
   - `*_COOKIES_PATH=/app/src/data/cookies/<file>` (опционально, только как явный override)
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
5. Подготовить `RELEASE_NOTES.md`:
   - добавить секцию релиза `vX.Y.Z`;
   - перенести в нее список реально выполненных задач/изменений.
6. Выполнить релизную чистку `IMPROVEMENTS.md`:
   - удалить из активного backlog только те задачи, которые уже отражены в `RELEASE_NOTES.md` этого релиза.
   - важно: очистка `IMPROVEMENTS.md` делается после фиксации задач в `RELEASE_NOTES.md`.
7. Прогнать проверку синхронизации:
   - `python scripts/release_sync.py --tag vX.Y.Z` (или `--write` для автосинхронизации метаданных).
8. Сделать финальный commit релиза (version + release notes + cleanup backlog).
9. Создать tag `vX.Y.Z` на этом commit.
10. Выполнить `git push` ветки и `git push` тега.

## Текущее ограничение

В runtime зарегистрированы `TikTokHandler`, `YouTubeHandler`, `InstagramHandler`, `CoubHandler`, `VKHandler`.  
`YandexMusic` handler присутствует в коде, но пока не подключен в `ServiceManager`.

## База данных

- Инициализация выполняется через SQLAlchemy (`Base.metadata.create_all`).
- Исторический модуль миграции удален из runtime-цепочки: проект ожидает актуальную схему БД.
- Основные таблицы: `bot_settings`, `sources`, `stats`.

## Деплой

- Серверный скрипт деплоя: `manager.sh`.
- Запуск: `./manager.sh dev` или `./manager.sh prod`.
- Скрипт ожидает env-файл на сервере по пути `$HOME/bot_{env}/.env` и валидирует обязательные ключи перед запуском контейнера.
- `bot.db` и cookies хранятся вне репозитория в `$HOME/bot_{env}/data/{db,cookies}` и монтируются в контейнер как volumes.
- В GitHub Actions deploy не управляет содержимым cookies: workflow подготавливает `$HOME/bot_{env}`, а `manager.sh` сам создает и монтирует `$HOME/bot_{env}/data/cookies` в контейнер как `/app/src/data/cookies` (read-only).
- Временные файлы создаются только внутри контейнера в `BOT_TEMP_DIR` (по умолчанию `/tmp/djgurda/temp_files`), включая отдельные подпапки по handler-классам.
- При старте бот инициализирует runtime-директории и удаляет устаревшие временные файлы; при остановке выполняется полная очистка временных файлов.
- `manager.sh` общий для `dev` и `prod`: любые правки должны сохранять совместимость перезапуска обоих окружений.
- Учитывай, что `prod` может временно отставать от `dev`, поэтому нельзя делать изменения, работающие только для одного окружения.

## Управление в чатах

- Команды `/start` и `/stop` разрешены для всех участников чата.
- Эти команды влияют только на флаг работы бота в текущем чате и не затрагивают другие чаты.
- Когда бот выключен в чате, он не обрабатывает другие сообщения и команды, кроме `/start`, `/stop`, `/toggle_bot`.
