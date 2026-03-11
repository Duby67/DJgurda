# AI Agent Project Context

## Project Summary

DJgurda Bot - асинхронный Telegram-бот для групповых чатов.  
Основной сценарий: пользователь отправляет ссылку на медиа-контент, бот извлекает/загружает контент и публикует его в унифицированном виде в чат. Целевая аудитория - участники Telegram-чатов, где нужны быстрые репосты контента из внешних платформ.

- Продуктовое допущение: приоритетный сценарий использования - через мобильные устройства (телефоны), поэтому UX ответов и медиа ориентирован на мобильный Telegram-клиент.

## Current Status

- Реализован рабочий pipeline на `aiogram 3.x` в polling-режиме.
- Активные стабильные обработчики в runtime: TikTok, YouTube, Instagram, COUB, Yandex Music (`ServiceManager` регистрирует `TikTokHandler`, `YouTubeHandler`, `InstagramHandler`, `CoubHandler`, `YandexMusicHandler`).
- VK Music присутствует в коде и dev/smoke-контуре, но сейчас не считается стабильным runtime-source.
- Текущая реализация `VK` считается недееспособной; `yt-dlp` не является рабочей базовой технологией для `VK`, поэтому источник остается в статусе `в разработке`.
- Обработчик Yandex Music подключен в stable runtime и поддерживает треки (`/track/<id>`) с возвратом `audio`.
- Есть SQLite-хранилище настроек чатов и статистики через async SQLAlchemy.
- CI/CD разворачивает Docker-образ в dev/prod окружения через GitHub Actions + SSH.
- Команды `/start` и `/stop` разрешены всем участникам чата; они меняют состояние бота только в текущем чате.
- При `bot_enabled=false` обработка сообщений в чате блокируется, кроме `/start`, `/stop`, `/toggle_bot`.
- `docs/` содержит поддерживаемые operational-документы (`docs/improvements.md`, `docs/release_notes.md`, `docs/deploy_layout.md`) и вторичные обзорные карты.
- `tests/` и `test/` в основном остаются legacy-зоной контекста, кроме согласованных локальных smoke-скриптов handlers:
  - `test/handlers/TikTok/test_tiktok_handlers_local.py` + `test/handlers/TikTok/TikTok_urls.py`
  - `test/handlers/YouTube/test_youtube_handlers_local.py` + `test/handlers/YouTube/YouTube_urls.py`
  - `test/handlers/Instagram/test_instagram_handlers_local.py` + `test/handlers/Instagram/Instagram_urls.py`
  - `test/handlers/Coub/test_coub_handlers_local.py` + `test/handlers/Coub/Coub_urls.py`
  - `test/handlers/VK/test_vk_handlers_local.py` + `test/handlers/VK/VK_urls.py`

## Source of Truth

Канонические источники:

- `README.md`
- `.github/ai-context.md`
- `docs/improvements.md`
- `docs/release_notes.md`
- `docs/deploy_layout.md`
- `src/**`
- `src/config.py`
- entrypoint-файлы:
  - `src/main.py`
  - `src/bot/lifespan/startup.py`
  - `src/bot/lifespan/shutdown.py`
- dependency-файлы:
  - `requirements.txt`
  - `requirements-dev.txt`
  - `deploy/Dockerfile`
  - `deploy/Dockerfile.dockerignore`

Дополнительно:

- В спорных местах источником истины является код в `src/**` и runtime-конфигурация из `src/config.py`.

## Repository Map

- `.github/workflows/` - CI/CD пайплайны (`deploy-dev.yml`, `deploy-prod.yml`).
- `deploy/` - deploy-артефакты репозитория (`deploy/Dockerfile`, `deploy/Dockerfile.dockerignore`, `deploy/manager.sh`, `deploy/sync_cookies.sh`, `deploy/sync_cookies.bat`, `deploy/sync_cookies.env.example`, `deploy/cookies/.gitkeep`).
- `.github/ai-agent-technical-task.md` - файл конкретного ТЗ для AI-агента; читать и выполнять только по прямому запросу пользователя, не использовать как источник контекста по умолчанию.
- `docs/improvements.md` - backlog улучшений, статусы задач и архитектурный follow-up.
- `docs/release_notes.md` - журнал заметных изменений для релизов и деплоя.
- `docs/deploy_layout.md` - схема размещения файлов в deploy-контуре и runtime-пути.
- `scripts/release_sync.py` - синхронизация релизного tag с `src.__version__`, `docs/release_notes.md` и `docs/improvements.md`.
- `src/main.py` - точка входа приложения.
- `src/config.py` - загрузка/валидация env и глобальные лимиты.
- `src/bot/commands/` - Telegram-команды.
- `src/bot/processing/` - извлечение ссылок, роутинг и отправка медиа.
- `src/bot/lifespan/` - startup/shutdown логика.
- `src/handlers/` - абстракции и платформенные обработчики.
- `src/handlers/mixins/` - legacy/shared low-level механики загрузки и валидации файлов; stable runtime движется к composition-based infrastructure вместо mixin-based слоя.
- `src/middlewares/bot_enabled.py` - middleware включения/отключения бота по чату.
- `src/middlewares/db/` - DB-ядро, модели и операции.
- `src/utils/` - вспомогательные утилиты (url, messages, logger, emoji).
- `src/data/` - runtime-артефакты проекта; `src/data/cookies` хранит runtime-оригиналы для текущего окружения, а в deploy `db` и `cookies` подключаются внешними volume.
- `deploy/manager.sh` - серверный запуск контейнера после деплоя.
  - `deploy/manager.sh` общий для `dev` и `prod`; изменения в нем должны оставаться совместимыми с перезапуском обоих окружений.
  - Удаленный доступ к серверу для AI-агентов запрещен (SSH/RDP/WinRM/remote shell). Любые server-side действия выполняет только пользователь.
  - Используй обычный UTF-8 без BOM; UTF-8 with BOM нежелателен.
  - учитывать, что `prod` может временно отставать от `dev`.

### Карта `src/`

- `src/` содержит основной код бота и runtime-контур.
- `src/bot/` содержит файлы взаимодействия с Telegram через `aiogram`.
- `src/data/` содержит runtime-файлы проекта (например, `db`, `cookies`) и локальные шаблонные артефакты для dev.
- `src/handlers/` содержит логику обработчиков: общие базовые механики и четкое взаимодействие с конкретными ресурсами.
- `src/middlewares/` содержит промежуточные скрипты; на текущем этапе в том числе слой работы с БД.
- `src/utils/` содержит общие утилиты и служебные модули, которые можно использовать в разных сегментах кода без нарушения архитектуры.

## Entrypoints

- Локальный запуск:
  - `python -m src.main`
- Runtime режим:
  - Polling через `Dispatcher.start_polling(...)`.
- Жизненный цикл:
  - startup: подготовка runtime-директорий (DB dir + temp root + per-handler temp dirs), очистка устаревших temp, DB init, уведомления о запуске.
  - shutdown: уведомления, полная очистка temp, закрытие DB.
- Webhook-режим:
  - Не реализован в текущем состоянии.

## Architecture

- `bot handlers`:
  - Командные роутеры в `src/bot/commands/*`.
  - Медиа-роутер в `src/bot/processing/media_router.py`.
- `services`:
  - `ServiceManager` выбирает platform handler по URL.
- `config`:
  - `src/config.py` централизованно валидирует критичные env.
- `storage/db`:
  - SQLite + SQLAlchemy async (`bot_settings`, `sources`, `stats`).
- `integrations`:
  - Telegram Bot API (aiogram),
  - `yt-dlp` + FFmpeg,
  - `aiohttp` для сетевых запросов/редиректов,
  - Yandex Music SDK (runtime handler подключен для треков).
- `states/middlewares`:
  - FSM states не используются.
  - middleware `BotEnabledMiddleware` управляет пропуском сообщений.

Связка модулей:
`main.py` -> middleware + routers -> `media_router` -> `resolve_url` -> `ServiceManager` -> handler `process()` -> отправка в Telegram -> `update_stats()`.

Рабочая runtime-граница:
`handler.process()` -> `MediaResult` -> sender/orchestration.

Переходный статус:
- В коде еще остается compatibility-слой для legacy `dict[file_info]`, но это не является целевым архитектурным состоянием.

## Configuration

Обязательные env-переменные (валидируются в `src/config.py`):

- `BOT_DB_PATH`
- `BOT_VERSION`
- `ADMIN_ID`
- `BOT_TOKEN`
- `YANDEX_MUSIC_TOKEN`

Директория временных файлов фиксирована:

- Runtime использует `src/data/runtime` (внутри контейнера: `/app/src/data/runtime`).
- Runtime создает эту директорию и поддиректории по handler-классам автоматически.

Условно-обязательная директория cookies (рекомендуемый режим):

- `COOKIES_DIR` (опционально; по умолчанию `src/data/cookies`)
- Если `*_COOKIES_PATH` не задан, используются файлы из `COOKIES_DIR`:
  - `www.youtube.com_cookies.txt`
  - `instagram_cookies.txt`
  - `tiktok_cookies.txt`
  - `vk.com_cookies.txt`
- `src/data/cookies` хранит runtime-оригиналы, с которыми бот работает в текущем окружении.
- `local/cookies` хранит локальные оригиналы cookies для локальных smoke-проверок и ручных тестов.
- `deploy/cookies` является deploy-источником cookies: в репозитории хранится только `deploy/cookies/.gitkeep`, реальные `*_cookies.txt` материализуются локально или в GitHub Actions из secrets перед деплоем.
- Для локальных smoke-проверок `test/handlers/*` валидные cookies автоматически копируются из `local/cookies` в `src/data/cookies`.
- Для deploy GitHub Actions при наличии secrets материализует `deploy/cookies` и синхронизирует только переданные файлы на сервер в `$HOME/bot_{env}/data/cookies` с перезаписью по совпадающим именам.
- Если secrets для cookies не заданы, deploy продолжает использовать уже существующие cookies в `$HOME/bot_{env}/data/cookies`.
- Для `yt-dlp` используется временная рабочая копия cookie-файла (`src/data/runtime/<HandlerClass>/runtime_*.txt`), оригинал не модифицируется; копия удаляется после выполнения.
- Для ручной загрузки deploy-cookies используются `deploy/sync_cookies.sh` и `deploy/sync_cookies.bat`: они только добавляют новые `*_cookies.txt` на сервер или перезаписывают одноименные, но не удаляют отсутствующие локально файлы.
- Параметры ручной синхронизации (`REMOTE_USER`, `REMOTE_HOST`, `REMOTE_PORT`) вынесены в локальный `deploy/sync_cookies.env`, который не должен попадать в git; шаблон хранится в `deploy/sync_cookies.env.example`.

Условно-обязательные для YouTube cookies:

- `YOUTUBE_COOKIES_ENABLED` (по умолчанию `true`)
- `YOUTUBE_COOKIES_PATH` (опционально; явный override, иначе `COOKIES_DIR/www.youtube.com_cookies.txt`)

Условно-обязательные для Instagram cookies:

- `INSTAGRAM_COOKIES_ENABLED` (по умолчанию `true`)
- `INSTAGRAM_COOKIES_PATH` (опционально; явный override, иначе `COOKIES_DIR/instagram_cookies.txt`)

Условно-обязательные для TikTok cookies:

- `TIKTOK_COOKIES_ENABLED` (по умолчанию `true`)
- `TIKTOK_COOKIES_PATH` (опционально; явный override, иначе `COOKIES_DIR/tiktok_cookies.txt`)

Условно-обязательные для VK cookies:

- `VK_COOKIES_ENABLED` (по умолчанию `true`)
- `VK_COOKIES_PATH` (опционально; явный override, иначе `COOKIES_DIR/vk.com_cookies.txt`)
- Локальный оригинал: `local/cookies/vk.com_cookies.txt`
- Deploy-источник: `deploy/cookies/vk.com_cookies.txt`
- Рабочий runtime-путь: `src/data/cookies/vk.com_cookies.txt`
- Историческое имя `vk_cookies.txt` больше не используется

Примечания по окружению:

- Эталон переменных окружения для разработки/проверок: `env.example`.
- Персональный `local/.env` не является частью проекта и не используется как источник истины.
- Локальная ОС разработки: Windows 11.
- Целевая ОС runtime: Ubuntu 24; возможны отличия поведения из-за различий ОС и shell-инструментов.
- Зависимости проекта устанавливаются в локальный `venv` в корне репозитория; системный Python не считать источником установленных проектных пакетов.

Опциональные:

- При `YOUTUBE_COOKIES_ENABLED=false` cookies принудительно отключены.
- При `YOUTUBE_COOKIES_ENABLED=true` handler автоматически использует валидный cookies-файл, если он доступен.
- Если cookies-файл выглядит как заглушка (пустой/без cookie-строк), handler игнорирует его.
- При `INSTAGRAM_COOKIES_ENABLED=false` Instagram cookies принудительно отключены.
- При `INSTAGRAM_COOKIES_ENABLED=true` handler автоматически использует валидный Instagram cookies-файл, если он доступен.
- Для части Instagram Stories без cookies возможна ошибка доступа (`You need to log in to access this content`).
- При `TIKTOK_COOKIES_ENABLED=false` TikTok cookies принудительно отключены.
- При `TIKTOK_COOKIES_ENABLED=true` handler автоматически использует валидный TikTok cookies-файл, если он доступен.
- При `VK_COOKIES_ENABLED=false` VK cookies принудительно отключены.
- При `VK_COOKIES_ENABLED=true` handler автоматически использует валидный VK cookies-файл, если он доступен.
- Если VK cookies-файл выглядит как заглушка (пустой/без cookie-строк), handler игнорирует его.
- Для локальных проверок VK рекомендуется использовать файл `vk.com_cookies.txt`.
- Для части VK Music ссылок без cookies возможна ошибка извлечения аудио URL/playlist metadata.
- Наличие VK cookies не означает readiness источника: `VK` остается dev/R&D-направлением.
- `yt-dlp` не считать рабочим решением для `VK`; любые новые задачи по `VK` трактовать как исследовательские, а не как обычную стабилизацию runtime-handler-а.

## Run & Development

Минимальный локальный контур:

1. Python 3.11+
2. FFmpeg в `PATH`
3. `pip install -r requirements.txt`
4. заполнить `.env`
5. `python -m src.main`

Примечания:

- В текущей политике проекта `tests/`/`test/` в целом не считаются поддерживаемой частью контекста и не являются обязательным шагом онбординга.
- Исключение для практической проверки handlers: используй локальные smoke-скрипты в `test/handlers/TikTok`, `test/handlers/YouTube`, `test/handlers/Instagram`, `test/handlers/Coub`, `test/handlers/VK`.
- Docker-запуск поддерживается через `deploy/Dockerfile`; `docker-compose.yml` сейчас отсутствует.
- Для локального запуска команд Python приоритет: `.\venv\Scripts\python.exe ...` (или активированный `venv`), а не системный `python`.

## Rule For Handler Smoke Tests

- Один обработчик = одна папка в `test/handlers/<Source>/`.
- Тестовый скрипт называется `test_<source>_handlers_local.py`.
- Все тестовые ссылки и ожидаемые типы хранятся только в `<Source>_urls.py` рядом с тестом.
- В теле теста ссылки не хардкодятся: данные читаются из `<Source>_urls.py`.
- Базовый сценарий smoke-теста:
  1. `resolve_url`.
  2. `ServiceManager.get_handler`.
  3. `handler.process(...)`.
  4. Проверка `MediaResult.content_type` на ожидаемый тип.
  5. Обязательная очистка временных файлов через `result.iter_cleanup_paths()` в `finally`.
- Временная compatibility-ветка для legacy результата допустима только если это явно требуется конкретной переходной задачей.
- Smoke-тесты handlers запускаются только в полном режиме обработки (без `--classify-only`).
- Любой запуск тестов (`pytest`, smoke-скрипты и т.п.) выполнять с повышенными правами только после явного запроса пользователю.

## Integrations

- Telegram API: `aiogram`.
- База данных: SQLite (`aiosqlite` + SQLAlchemy async ORM).
- Внешние медиа-источники: через `yt-dlp` и конкретные handlers.
- Yandex Music: SDK используется active runtime-handler-ом для обработки track-ссылок.
- VK Music: текущий код использует web/mobile extraction через async HTTP + optional cookies, но источник остается в статусе `в разработке`; текущая реализация недееспособна, `yt-dlp` не является рабочей базой для `VK`.
- URL resolving: `aiohttp` (HEAD/GET redirects).
- Deployment: GitHub Actions + GHCR + SSH deploy script (`deploy/manager.sh`).
- В `deploy/manager.sh` включена ротация резервных копий БД в `$HOME/bot_{env}/data/db/backups` (параметр хранения: `DB_BACKUP_KEEP_COUNT`, по умолчанию `14`).
- В deploy workflows cookies могут материализоваться на runner в `deploy/cookies` из опциональных secrets `YOUTUBE_COOKIES_FILE`, `INSTAGRAM_COOKIES_FILE`, `TIKTOK_COOKIES_FILE`, `VK_COOKIES_FILE`, `COUB_COOKIES_FILE`.
- Затем workflow очищает только staging-папку `$HOME/deploy/cookies`, копирует туда текущее содержимое `deploy/cookies` и, если там есть `*_cookies.txt`, перезаписывает только одноименные файлы в `$HOME/bot_{env}/data/cookies`.
- Если secrets для cookies не заданы, deploy не должен падать: контейнер продолжает использовать существующие server-side cookies volume.
- `bot.db` хранится снаружи контейнера в `$HOME/bot_{env}/data/db` и монтируется в `/app/src/data/db`.
- Legacy-инициализация `runtime` в Docker/deploy удалена: временные директории создаются runtime-кодом Python внутри контейнера (`/app/src/data/runtime`), без внешнего volume.

## Known Issues / Gaps

- `VK` не является стабильным runtime-source; текущая реализация недееспособна и требует отдельного R&D без опоры на `yt-dlp`.
- `docker-compose.yml` отсутствует, хотя упоминался в старых описаниях.
- В текущем `.env` может отсутствовать `BOT_DB_PATH`; это ломает старт.
- Нет явного контроля прав для команд управления состоянием бота в чатах.
- Webhook-режим не реализован.

## Legacy / Ignored Areas

- Обзорные карты в `docs/` (`docs/repository-root-map.md`, `docs/documentation-sources.md`) - вторичный слой навигации; при расхождении источником истины остаются `README.md`, `.github/ai-context.md`, `docs/improvements.md` и код.
- `tests/` / `test/` - legacy зона на текущем этапе; не используется как источник актуального контекста, кроме согласованных smoke-скриптов handlers в `test/handlers/TikTok`, `test/handlers/YouTube`, `test/handlers/Instagram`, `test/handlers/Coub`, `test/handlers/VK`.
- `venv/`, `__pycache__/`, `.env` - локальные артефакты окружения; не считать источником проектной правды даже если они присутствуют в рабочей директории.
- Старые markdown-артефакты вне `README.md` и `.github/ai-context.md` считать вторичными/историческими, если они не синхронизированы с кодом.

## Instructions for AI Agents

1. Перед началом правок убедись, что активна ветка `dev`; любые взаимодействия с репозиторием выполнять только в `dev`, доступ к ветке `main` запрещен.
2. Сначала читай `README.md` и `.github/ai-context.md`.
3. При любом обращении к `README.md` обязательно дополнительно проверяй `docs/improvements.md`.
4. Файл `.github/ai-agent-technical-task.md` не читать и не выполнять автоматически; обращаться к нему только по прямому запросу пользователя на выполнение конкретного ТЗ.
5. Если работа ведется по `.github/ai-agent-technical-task.md`, все выполненные пункты нужно:
   - пометить как `Выполнено` в самом task-файле;
   - отразить в `docs/improvements.md`.
6. Перед внесением любых правок в код обязательно сверяйся с `docs/improvements.md`; если планируемые или уже выполненные изменения там не отражены, добавь их в backlog и только после этого продолжай работу.
7. Затем сверяй контекст по реальному коду.
8. Больше доверяй коду и config-файлам, чем старым markdown-документам.
9. Не считай обзорные карты в `docs/` актуальным источником правды; поддерживаемыми документами там являются `docs/improvements.md`, `docs/release_notes.md` и `docs/deploy_layout.md`. `tests/` и `test/` также не считать источником правды, кроме согласованных smoke-скриптов проверки handlers (`test/handlers/TikTok`, `test/handlers/YouTube`, `test/handlers/Instagram`, `test/handlers/Coub`, `test/handlers/VK`).
10. Не анализируй `venv/`, `__pycache__/` и `.env` как источник контекста проекта.
11. Не выдумывай отсутствующие фичи.
12. Если что-то непонятно - фиксируй это в разделе gaps, а не домысливай.
13. Вноси изменения минимально и локально, не ломая существующую структуру.
14. Основной язык в `.md` файлах - русский; типовые и служебные заголовки допустимы на английском.
15. Комментарии в example-файлах, Dockerfile/`.dockerignore`-файлах, dotfiles, коде и скриптах должны быть на русском языке.
16. Все сообщения, выводимые в консоль, должны быть на английском языке.
17. Все лог-сообщения и технические runtime-сообщения должны быть на английском языке.
18. В конце обработки, после завершения всех правок, предлагай commit message на английском в формате готовой для копирования, пример "docs: update release workflow and backlog sync".
19. Все выполненные задачи обязательно сверяй с `docs/improvements.md` и обновляй там статус; при релизной чистке выполненные задачи удаляй из активного backlog.
20. Для релизов с tag используй `python scripts/release_sync.py --tag <tag>` (и `--write` при необходимости обновить шаблоны файлов).
21. При запросе на выпуск новой версии действуй по процедуре:
22. При изменении `.md` файлов соблюдай единый стиль markdownlint: ориентируйся на `.markdownlint.json`, исключения из `.markdownlintignore` и перед финализацией проверяй `npx.cmd markdownlint-cli2 "**/*.md" ".github/*.md"`.
    - Важно: `markdownlint-cli2` в текущей среде стабильно упирается в sandbox/npm cache, поэтому этот запуск всегда выполняй вне ограничений и всегда запрашивай для него разрешение у пользователя.
23. В пользовательских caption удаляй хэштеги из заголовков; если после очистки заголовок пустой, используй нейтральный fallback-текст вместо исходного набора хэштегов.
24. Если важный скрипт/тулза не запускается из-за ограничений среды (sandbox, права, сеть), запрашивай повышение прав у пользователя вместо молчаливого пропуска шага.
25. Для всех локальных Python-команд и проверок используй проектный `venv` (`.\venv\Scripts\python.exe` или активированный `venv`), не полагайся на системный Python.
26. Любые тесты (`pytest`, локальные smoke-скрипты handlers, интеграционные прогоны) запускай только с повышенными правами после явного запроса пользователю.
27. Удаленный доступ к серверу для AI-агентов запрещен (SSH/RDP/WinRM/remote shell). Любые server-side действия выполняет только пользователь.
28. Используй обычный UTF-8 без BOM; UTF-8 with BOM нежелателен.

- убедись, что у пользователя нет незакоммиченных изменений (или явно подтвердил, что их можно включить в релиз);
- синхронизируй `dev` с `origin/dev` и убедись, что актуальные изменения в `dev` запушены;
- не переключайся в `main` и не выполняй операций в этой ветке: доступ к `main` запрещен для AI-агента (merge в `main` выполняется владельцем вручную вне задач агента);
- повысь `__version__` в `src/__init__.py` по схеме `major.minor.patch`, где каждое число 0..9:
  - если `patch < 9`: `patch += 1`;
  - если `patch == 9`: `patch = 0`, `minor += 1`;
  - если `minor == 9` и был перенос: `minor = 0`, `major += 1`;
- обнови `docs/release_notes.md` по выполненным задачам текущего релиза;
- выполни релизную чистку `docs/improvements.md` только после переноса этих задач в `docs/release_notes.md`;
- проверь синхронизацию через `python scripts/release_sync.py --tag vX.Y.Z` (при необходимости `--write`);
- сделай финальный commit релиза (version + release notes + cleanup backlog);
- создай tag формата `vX.Y.Z` на финальном commit и обеспечь соответствие `__version__ == X.Y.Z`;
- после этого передай пользователю изменения на финальный push ветки и тега.

Дополнительные рабочие правила:

- Начинай анализ с `src/main.py`, `src/config.py`, `src/bot/processing/*`, `src/handlers/manager.py`, `src/middlewares/db/*`.
- При расхождении документации и кода выбирай код и обновляй этот файл.
- Новые найденные проблемы добавляй в `Known Issues / Gaps` этого файла.
- Не подключай новые handlers в runtime без явной проверки end-to-end и env-требований.

## Next Recommended Steps

1. Определить политику прав доступа к командам переключения (`/toggle_*`, `/start`, `/stop`), если текущее поведение нужно ужесточить.
2. Вынести `VK` в отдельный R&D-трек без опоры на `yt-dlp`.
3. При необходимости добавить webhook-режим.
