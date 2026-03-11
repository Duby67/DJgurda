# DJgurda Bot

Асинхронный Telegram-бот для обработки медиа-ссылок в чатах.  
Текущий рабочий контур поддерживает:

- TikTok (`video`, `profile`, `media_group`)
- YouTube (`shorts`, `channel`)
- Instagram (`reels`, `media_group`, `stories`, `profile`)
- COUB (`video`)
- Yandex Music (`audio` для ссылок `track`)

Дополнительно по статусам источников:

- `VK Music` присутствует в коде как источник `в разработке`, но не считается частью текущего стабильного runtime-контура.
- Текущая реализация `VK` считается недееспособной; `yt-dlp` не рассматривается как рабочая базовая технология для `VK`.
- `YandexMusic` зарегистрирован в стабильном runtime-контуре и обрабатывает track-ссылки в тип `audio`.

Бот сохраняет статистику по чатам и пользователям.

## Продуктовое допущение (mobile-first)

- Основной сценарий использования бота и просмотра полученного контента - мобильный клиент Telegram на телефонах.
- При проектировании форматов ответов, подписей и медиа-групп приоритет отдается удобству чтения и просмотра на экранах смартфонов.

## Главный контекст проекта

Основной источник контекста для разработчиков и AI-агентов:

- [`.github/ai-context.md`](./.github/ai-context.md)
- [`docs/improvements.md`](./docs/improvements.md)

Политика актуальности:

- `README.md` и `.github/ai-context.md` - канонические документы верхнего уровня.
- `docs/improvements.md`, `docs/release_notes.md` и `docs/deploy_layout.md` - поддерживаемые operational-документы.
- Контекст всегда проверяется по коду в `src/`.
- При любом обращении к `README.md` агент обязан дополнительно проверить `.github/ai-context.md` и `docs/improvements.md`.
- В пользовательских caption хэштеги из заголовков контента должны удаляться; если заголовок после очистки пустой, используется нейтральный fallback-текст.

## Важный статус по структуре

- `docs/` используется как каталог поддерживаемой документации верхнего уровня.
- Каноничность внутри `docs/` определяется конкретными файлами: `docs/improvements.md`, `docs/release_notes.md` и `docs/deploy_layout.md` поддерживаются; обзорные карты в `docs/` остаются вторичными.
- Active orchestration-контур уже опирается на typed runtime boundary (`MediaResult`); legacy compatibility-слой пока еще присутствует в коде как переходный слой.
- `test/` Содержит скрипты для локальной проверки.
  - `test/handlers/` smoke-скрипты для локальной проверки handlers.
  - Все тесты (`pytest` и smoke-скрипты) запускать только с повышенными правами после явного подтверждения пользователя.

## Карта `src/`

- `src/` содержит основной код бота и runtime-контур.
- `src/bot/` содержит файлы взаимодействия с Telegram через `aiogram`.
- `src/data/` содержит runtime-файлы проекта (например, `db`, `cookies`) и локальные шаблонные артефакты для dev.
- `src/handlers/` содержит логику обработчиков: общие базовые механики и четкое взаимодействие с конкретными ресурсами.
- `src/middlewares/` содержит промежуточные скрипты; на текущем этапе в том числе слой работы с БД.
- `src/utils/` содержит общие утилиты и служебные модули, которые можно использовать в разных сегментах кода без нарушения архитектуры.

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

   Runtime-директория временных файлов фиксирована в `src/config.py`:
   - `src/data/runtime` (внутри контейнера: `/app/src/data/runtime`)

   Общая директория cookies (рекомендуемый режим):
   - `COOKIES_DIR` (опционально; по умолчанию `src/data/cookies`)
   - Если `*_COOKIES_PATH` не задан, обработчик автоматически ищет cookies в `COOKIES_DIR`:
     - `www.youtube.com_cookies.txt`
     - `instagram_cookies.txt`
     - `tiktok_cookies.txt`
     - `vk.com_cookies.txt`
   - `src/data/cookies` хранит runtime-оригиналы, с которыми бот работает в текущем окружении.
   - `local/cookies` хранит локальные оригиналы cookies для локальных smoke-проверок и ручных тестов.
   - `deploy/cookies` является deploy-источником cookies: в git хранится только `deploy/cookies/.gitkeep`, реальные `*_cookies.txt` материализуются локально или в GitHub Actions из secrets перед деплоем.
   - Для локальных smoke-проверок `test/handlers/*` валидные cookies автоматически копируются из `local/cookies` в `src/data/cookies`.
   - Для deploy GitHub Actions при наличии secrets материализует `deploy/cookies` и синхронизирует только переданные файлы на сервер в `$HOME/bot_{env}/data/cookies` с перезаписью по совпадающим именам.
   - Если secrets для cookies не заданы, deploy продолжает использовать уже существующие cookies в `$HOME/bot_{env}/data/cookies`.
   - Для `yt-dlp` используется временная рабочая копия cookie-файла (`src/data/runtime/<HandlerClass>/runtime_*.txt`), оригинал не модифицируется; копия удаляется после выполнения.
   - Для ручной загрузки deploy-cookies используй `deploy/sync_cookies.sh` или `deploy/sync_cookies.bat`: эти скрипты только добавляют новые `*_cookies.txt` на сервер или перезаписывают одноименные, но не удаляют отсутствующие локально файлы.
   - Параметры ручной синхронизации (`REMOTE_USER`, `REMOTE_HOST`, `REMOTE_PORT`) хранятся в локальном `deploy/sync_cookies.env`, который не попадает в git; шаблон лежит в `deploy/sync_cookies.env.example`.

   Опционально для YouTube cookies:
   - `YOUTUBE_COOKIES_ENABLED` (`true/false`, по умолчанию `true`)
   - `YOUTUBE_COOKIES_PATH` (опционально; явный override, иначе используется `COOKIES_DIR/www.youtube.com_cookies.txt`)

   Важное замечание:
   - Если `www.youtube.com_cookies.txt` является заглушкой (пустой или без валидных cookie-строк), YouTube handler автоматически игнорирует этот файл.
   - По умолчанию handler пытается использовать валидный cookies-файл (если он доступен).
   - Для принудительного отключения cookies установи `YOUTUBE_COOKIES_ENABLED=false`.

   Опционально для Instagram cookies:
   - `INSTAGRAM_COOKIES_ENABLED` (`true/false`, по умолчанию `true`)
   - `INSTAGRAM_COOKIES_PATH` (опционально; явный override, иначе используется `COOKIES_DIR/instagram_cookies.txt`)

   Важное замечание:
   - Для части Instagram Stories требуется авторизация; без валидных Instagram cookies возможна ошибка доступа (`You need to log in to access this content`).

   Опционально для TikTok cookies:
   - `TIKTOK_COOKIES_ENABLED` (`true/false`, по умолчанию `true`)
   - `TIKTOK_COOKIES_PATH` (опционально; явный override, иначе используется `COOKIES_DIR/tiktok_cookies.txt`)

   Опционально для VK cookies:
   - `VK_COOKIES_ENABLED` (`true/false`, по умолчанию `true`)
   - `VK_COOKIES_PATH` (опционально; явный override, иначе используется `COOKIES_DIR/vk.com_cookies.txt`)
   - Локальный оригинал: `local/cookies/vk.com_cookies.txt`
   - Deploy-источник: `deploy/cookies/vk.com_cookies.txt`
   - Рабочий runtime-путь: `src/data/cookies/vk.com_cookies.txt`
   - Историческое имя `vk_cookies.txt` больше не используется

   Важное замечание:
   - Эти параметры сохраняются для dev/R&D сценариев `VK` и не означают, что `VK` является стабильным runtime-источником.
   - Для части VK Music ссылок требуется авторизованная сессия; без валидных VK cookies обработчик может не извлечь audio URL/playlist metadata.
   - Если `vk.com_cookies.txt` пустой или выглядит как заглушка, VK handler автоматически игнорирует его.
   - Текущая реализация `VK` считается недееспособной; `yt-dlp` не является рабочей базой для `VK`.

   Шаблон:
   - `env.example` (скопируй в `.env` и подставь значения).
   - Для локальных проверок и тестовых сценариев ориентируйся на `env.example` как на эталонный набор переменных.
   - Персональный файл `local/.env` не является частью проекта и не должен использоваться как источник проектного контекста.

   Для Docker/deploy используются значения путей внутри контейнера:
   - `BOT_DB_PATH=/app/src/data/db/bot.db`
   - `COOKIES_DIR=/app/src/data/cookies`
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
- `.github/workflows/*` и `deploy/` - CI/CD и deploy-артефакты.

## Команды бота

- `/help` - список активных стабильных источников.
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

- [`docs/deploy_layout.md`](./docs/deploy_layout.md)

## Release Notes

- [`docs/release_notes.md`](./docs/release_notes.md)

## Релизная синхронизация версии

- Источник версии в коде: `src/__init__.py` (`__version__`).
- Для релиза в `prod` рекомендуется ставить tag на тот же commit (например, `v1.2.0`).
- Скрипт проверки/подготовки релиза:
  - проверяет соответствие `__version__` и tag;
  - проверяет наличие секции в `docs/release_notes.md`;
  - проверяет/обновляет метку ревизии backlog в `docs/improvements.md`.

Проверка (без изменений файлов):

```bash
python scripts/release_sync.py --tag v1.2.0
```

Автодобавление шаблона в `docs/release_notes.md` и обновление ревизии в `docs/improvements.md`:

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
5. Подготовить `docs/release_notes.md`:
   - добавить секцию релиза `vX.Y.Z`;
   - перенести в нее список реально выполненных задач/изменений.
6. Выполнить релизную чистку `docs/improvements.md`:
   - удалить из активного backlog только те задачи, которые уже отражены в `docs/release_notes.md` этого релиза.
   - важно: очистка `docs/improvements.md` делается после фиксации задач в `docs/release_notes.md`.
7. Прогнать проверку синхронизации:
   - `python scripts/release_sync.py --tag vX.Y.Z` (или `--write` для автосинхронизации метаданных).
8. Сделать финальный commit релиза (version + release notes + cleanup backlog).
9. Создать tag `vX.Y.Z` на этом commit.
10. Выполнить `git push` ветки и `git push` тега.

## Статусы источников

- В стабильном runtime зарегистрированы `TikTokHandler`, `YouTubeHandler`, `InstagramHandler`, `CoubHandler`, `YandexMusicHandler`.
- `VKHandler` присутствует в коде и test/dev-контуре, но не считается частью стабильного runtime.
- Текущая реализация `VK` недееспособна; `yt-dlp` не рассматривается как рабочая базовая технология для `VK`, поэтому для источника требуется отдельный R&D.

## База данных

- Инициализация выполняется через SQLAlchemy (`Base.metadata.create_all`).
- Исторический модуль миграции удален из runtime-цепочки: проект ожидает актуальную схему БД.
- Основные таблицы: `bot_settings`, `sources`, `stats`.

## Деплой

- Серверный скрипт деплоя в репозитории: `deploy/manager.sh`.
- Запуск на сервере: `./deploy/manager.sh dev` или `./deploy/manager.sh prod`.
- Скрипт ожидает env-файл на сервере по пути `$HOME/bot_{env}/.env` и валидирует обязательные ключи перед запуском контейнера.
- `bot.db` и cookies хранятся вне репозитория в `$HOME/bot_{env}/data/{db,cookies}` и монтируются в контейнер как volumes.
- Для Docker build используется `deploy/Dockerfile` и связанный ignore-файл `deploy/Dockerfile.dockerignore`.
- В GitHub Actions deploy может материализовать `deploy/cookies` на runner из опциональных secrets `YOUTUBE_COOKIES_FILE`, `INSTAGRAM_COOKIES_FILE`, `TIKTOK_COOKIES_FILE`, `VK_COOKIES_FILE`, `COUB_COOKIES_FILE`.
- Workflow очищает только staging-папку `$HOME/deploy/cookies`, затем копирует туда текущее содержимое `deploy/cookies`.
- Если в staging есть `*_cookies.txt`, workflow перезаписывает только одноименные файлы в `$HOME/bot_{env}/data/cookies`.
- Если secrets для cookies не переданы и в staging нет `*_cookies.txt`, deploy не падает и контейнер продолжает использовать существующие server-side cookies volume.
- `deploy/manager.sh` создает и монтирует `$HOME/bot_{env}/data/cookies` в контейнер как `/app/src/data/cookies` (read-only).
- Для ручной синхронизации cookies в deploy-контуре доступны `deploy/sync_cookies.sh` и `deploy/sync_cookies.bat`.
- Параметры подключения для этих скриптов вынесены в локальный `deploy/sync_cookies.env`; в репозитории хранится только `deploy/sync_cookies.env.example`.
- Временные файлы создаются только внутри контейнера в `/app/src/data/runtime` (фиксированный путь), включая отдельные подпапки по handler-классам.
- При старте бот инициализирует runtime-директории и удаляет устаревшие временные файлы; при остановке выполняется полная очистка временных файлов.
- `deploy/manager.sh` общий для `dev` и `prod`: любые правки должны сохранять совместимость перезапуска обоих окружений.
- Удаленный доступ к серверу для AI-агентов запрещен (SSH/RDP/WinRM/remote shell). Любые server-side действия выполняет только пользователь.
- Для кодировки используйте обычный UTF-8 без BOM; UTF-8 with BOM нежелателен.
- В `deploy/manager.sh` включена ротация резервных копий БД: бэкапы пишутся в `$HOME/bot_{env}/data/db/backups`, хранение регулируется `DB_BACKUP_KEEP_COUNT` (по умолчанию `14`).
- Учитывай, что `prod` может временно отставать от `dev`, поэтому нельзя делать изменения, работающие только для одного окружения.

## Управление в чатах

- Команды `/start` и `/stop` разрешены для всех участников чата.
- Эти команды влияют только на флаг работы бота в текущем чате и не затрагивают другие чаты.
- Когда бот выключен в чате, он не обрабатывает другие сообщения и команды, кроме `/start`, `/stop`, `/toggle_bot`.
