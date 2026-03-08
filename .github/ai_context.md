# AI Context

## Project Summary

DJgurda Bot - асинхронный Telegram-бот для групповых чатов.  
Основной сценарий: пользователь отправляет ссылку на медиа-контент, бот извлекает/загружает контент и публикует его в унифицированном виде в чат. Целевая аудитория - участники Telegram-чатов, где нужны быстрые репосты контента из внешних платформ.

- Продуктовое допущение: приоритетный сценарий использования - через мобильные устройства (телефоны), поэтому UX ответов и медиа ориентирован на мобильный Telegram-клиент.

## Current Status

- Реализован рабочий pipeline на `aiogram 3.x` в polling-режиме.
- Активные обработчики в runtime: TikTok, YouTube, Instagram, COUB, VK Music (`ServiceManager` регистрирует `TikTokHandler`, `YouTubeHandler`, `InstagramHandler`, `CoubHandler`, `VKHandler`).
- Обработчик Yandex Music присутствует в коде, но сейчас отключен в менеджере.
- Есть SQLite-хранилище настроек чатов и статистики через async SQLAlchemy.
- CI/CD разворачивает Docker-образ в dev/prod окружения через GitHub Actions + SSH.
- Команды `/start` и `/stop` разрешены всем участникам чата; они меняют состояние бота только в текущем чате.
- При `bot_enabled=false` обработка сообщений в чате блокируется, кроме `/start`, `/stop`, `/toggle_bot`.
- `docs/` не используются как поддерживаемые источники контекста на текущем этапе.
- `tests/` и `test/` в основном остаются legacy-зоной контекста, кроме согласованных локальных smoke-скриптов handlers:
  - `test/handlers/TikTok/test_tiktok_handlers_local.py` + `test/handlers/TikTok/TikTok_urls.py`
  - `test/handlers/YouTube/test_youtube_handlers_local.py` + `test/handlers/YouTube/YouTube_urls.py`
  - `test/handlers/Instagram/test_instagram_handlers_local.py` + `test/handlers/Instagram/Instagram_urls.py`
  - `test/handlers/Coub/test_coub_handlers_local.py` + `test/handlers/Coub/Coub_urls.py`
  - `test/handlers/VK/test_vk_handlers_local.py` + `test/handlers/VK/VK_urls.py`

## Source of Truth

Канонические источники:

- `README.md`
- `.github/ai_context.md`
- `IMPROVEMENTS.md`
- `src/**`
- `src/config.py`
- entrypoint-файлы:
  - `src/main.py`
  - `src/bot/lifespan/startup.py`
  - `src/bot/lifespan/shutdown.py`
- dependency-файлы:
  - `requirements.txt`
  - `requirements-dev.txt`
  - `Dockerfile`

Дополнительно:

- В спорных местах источником истины является код в `src/**` и runtime-конфигурация из `src/config.py`.

## Repository Map

- `.github/workflows/` - CI/CD пайплайны (`deploy-dev.yml`, `deploy-prod.yml`).
- `RELEASE_NOTES.md` - журнал заметных изменений для релизов и деплоя.
- `scripts/release_sync.py` - синхронизация релизного tag с `src.__version__`, `RELEASE_NOTES.md` и `IMPROVEMENTS.md`.
- `src/main.py` - точка входа приложения.
- `src/config.py` - загрузка/валидация env и глобальные лимиты.
- `src/bot/commands/` - Telegram-команды.
- `src/bot/processing/` - извлечение ссылок, роутинг и отправка медиа.
- `src/bot/lifespan/` - startup/shutdown логика.
- `src/handlers/` - абстракции и платформенные обработчики.
- `src/handlers/mixins/` - общие механики загрузки/валидации файлов.
- `src/middlewares/bot_enabled.py` - middleware включения/отключения бота по чату.
- `src/middlewares/db/` - DB-ядро, модели и операции.
- `src/utils/` - вспомогательные утилиты (url, messages, logger, emoji).
- `src/data/` - только шаблонные локальные runtime-артефакты для dev; в deploy `db` и `cookies` подключаются внешними volume.
- `manager.sh` - серверный запуск контейнера после деплоя.
  - `manager.sh` общий для `dev` и `prod`; изменения в нем должны оставаться совместимыми с перезапуском обоих окружений.
  - учитывать, что `prod` может временно отставать от `dev`.

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
  - Yandex Music SDK (код есть, но runtime handler не подключен).
- `states/middlewares`:
  - FSM states не используются.
  - middleware `BotEnabledMiddleware` управляет пропуском сообщений.

Связка модулей:
`main.py` -> middleware + routers -> `media_router` -> `resolve_url` -> `ServiceManager` -> handler `process()` -> отправка в Telegram -> `update_stats()`.

## Configuration

Обязательные env-переменные (валидируются в `src/config.py`):

- `BOT_DB_PATH`
- `BOT_VERSION`
- `ADMIN_ID`
- `BOT_TOKEN`
- `YANDEX_MUSIC_TOKEN`

Условно-обязательная директория временных файлов:

- `BOT_TEMP_DIR` (опционально; по умолчанию системный temp-dir, например `/tmp/djgurda/temp_files` в Docker)
- Runtime создает `BOT_TEMP_DIR` и поддиректории по handler-классам автоматически.

Условно-обязательная директория cookies (рекомендуемый режим):

- `COOKIES_DIR` (опционально; по умолчанию `src/data/cookies`)
- Если `*_COOKIES_PATH` не задан, используются файлы из `COOKIES_DIR`:
  - `youtube_cookies.txt`
  - `instagram_cookies.txt`
  - `vk.com_cookies.txt`
- Оригинальные локальные cookies-файлы рекомендуется хранить в `local/cookies` (папка вне git-индекса).
- Для локальных smoke-проверок `test/handlers/*` валидные cookies автоматически копируются из `local/cookies` в `src/data/cookies`.
- Для `yt-dlp` используется временная рабочая копия cookie-файла, оригинал не модифицируется.

Условно-обязательные для YouTube cookies:

- `YOUTUBE_COOKIES_ENABLED` (по умолчанию `true`)
- `YOUTUBE_COOKIES_PATH` (опционально; явный override, иначе `COOKIES_DIR/youtube_cookies.txt`)

Условно-обязательные для Instagram cookies:

- `INSTAGRAM_COOKIES_ENABLED` (по умолчанию `true`)
- `INSTAGRAM_COOKIES_PATH` (опционально; явный override, иначе `COOKIES_DIR/instagram_cookies.txt`)

Условно-обязательные для VK cookies:

- `VK_COOKIES_ENABLED` (по умолчанию `true`)
- `VK_COOKIES_PATH` (опционально; явный override, иначе `COOKIES_DIR/vk.com_cookies.txt`)
- Рекомендуемый путь оригинального файла: `local/cookies/vk.com_cookies.txt`
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
- При `VK_COOKIES_ENABLED=false` VK cookies принудительно отключены.
- При `VK_COOKIES_ENABLED=true` handler автоматически использует валидный VK cookies-файл, если он доступен.
- Если VK cookies-файл выглядит как заглушка (пустой/без cookie-строк), handler игнорирует его.
- Для локальных проверок VK рекомендуется использовать файл `vk.com_cookies.txt`.
- Для части VK Music ссылок без cookies возможна ошибка извлечения аудио URL/playlist metadata.

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
- Docker-запуск поддерживается через `Dockerfile`; `docker-compose.yml` сейчас отсутствует.
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
  4. Проверка `file_info["type"]` на ожидаемый тип.
  5. Обязательный `handler.cleanup(file_info)` в `finally`.
- Smoke-тесты handlers запускаются только в полном режиме обработки (без `--classify-only`).
- Любой запуск тестов (`pytest`, smoke-скрипты и т.п.) выполнять с повышенными правами только после явного запроса пользователю.

## Integrations

- Telegram API: `aiogram`.
- База данных: SQLite (`aiosqlite` + SQLAlchemy async ORM).
- Внешние медиа-источники: через `yt-dlp` и конкретные handlers.
- Yandex Music: SDK подключен в коде handler, но handler в runtime отключен.
- VK Music: web/mobile extraction через async HTTP + optional cookies; handler подключен в runtime.
- URL resolving: `aiohttp` (HEAD/GET redirects).
- Deployment: GitHub Actions + GHCR + SSH deploy script (`manager.sh`).
- В deploy workflows cookies не копируются автоматически: `manager.sh` создает `$HOME/bot_{env}/data/cookies` и монтирует его в контейнер как `/app/src/data/cookies` (read-only).
- `bot.db` хранится снаружи контейнера в `$HOME/bot_{env}/data/db` и монтируется в `/app/src/data/db`.
- Legacy-инициализация `temp_files` в Docker/deploy удалена: временные директории создаются runtime-кодом Python внутри контейнера (`BOT_TEMP_DIR`), без внешнего volume.

## Known Issues / Gaps

- В runtime пока не подключен Yandex Music handler.
- `docker-compose.yml` отсутствует, хотя упоминался в старых описаниях.
- В текущем `.env` может отсутствовать `BOT_DB_PATH`; это ломает старт.
- Нет явного контроля прав для команд управления состоянием бота в чатах.
- Webhook-режим не реализован.

## Legacy / Ignored Areas

- `docs/` - legacy зона; не используется как источник актуальной информации.
- `tests/` / `test/` - legacy зона на текущем этапе; не используется как источник актуального контекста, кроме согласованных smoke-скриптов handlers в `test/handlers/TikTok`, `test/handlers/YouTube`, `test/handlers/Instagram`, `test/handlers/Coub`, `test/handlers/VK`.
- `venv/`, `__pycache__/`, `.env` - локальные артефакты окружения; не считать источником проектной правды даже если они присутствуют в рабочей директории.
- Старые markdown-артефакты вне `README.md` и `.github/ai_context.md` считать вторичными/историческими, если они не синхронизированы с кодом.

## Instructions for AI Agents

1. Перед началом правок убедись, что активна ветка `dev`; любые взаимодействия с репозиторием выполнять только в `dev`, доступ к ветке `main` запрещен.
2. Сначала читай `README.md` и `.github/ai_context.md`.
3. При любом обращении к `README.md` обязательно дополнительно проверяй `IMPROVEMENTS.md`.
4. Перед внесением любых правок в код обязательно сверяйся с `IMPROVEMENTS.md`; если планируемые или уже выполненные изменения там не отражены, добавь их в backlog и только после этого продолжай работу.
5. Затем сверяй контекст по реальному коду.
6. Больше доверяй коду и config-файлам, чем старым markdown-документам.
7. Не считай `docs/` и `tests/` актуальным источником правды, кроме согласованных smoke-скриптов проверки handlers (`test/handlers/TikTok`, `test/handlers/YouTube`, `test/handlers/Instagram`, `test/handlers/Coub`, `test/handlers/VK`).
8. Не анализируй `venv/`, `__pycache__/` и `.env` как источник контекста проекта.
9. Не выдумывай отсутствующие фичи.
10. Если что-то непонятно - фиксируй это в разделе gaps, а не домысливай.
11. Вноси изменения минимально и локально, не ломая существующую структуру.
12. Язык комментариев и всех человеко-читаемых проектных файлов - русский.
13. Логи, технические runtime-сообщения и похожие служебные сегменты - английский.
14. В конце обработки, после завершения всех правок, предлагай commit message на английском в формате готовой для копирования, пример "docs: update release workflow and backlog sync".
15. Все выполненные задачи обязательно сверяй с `IMPROVEMENTS.md` и обновляй там статус; при релизной чистке выполненные задачи удаляй из активного backlog.
16. Для релизов с tag используй `python scripts/release_sync.py --tag <tag>` (и `--write` при необходимости обновить шаблоны файлов).
17. При запросе на выпуск новой версии действуй по процедуре:
18. При изменении `.md` файлов соблюдай единый стиль markdownlint: ориентируйся на `.markdownlint.json`, исключения из `.markdownlintignore` и перед финализацией проверяй `npx.cmd markdownlint-cli2 "**/*.md" ".github/*.md"`.
19. В пользовательских caption удаляй хэштеги из заголовков; если после очистки заголовок пустой, используй нейтральный fallback-текст вместо исходного набора хэштегов.
20. Если важный скрипт/тулза не запускается из-за ограничений среды (sandbox, права, сеть), запрашивай повышение прав у пользователя вместо молчаливого пропуска шага.
21. Для всех локальных Python-команд и проверок используй проектный `venv` (`.\venv\Scripts\python.exe` или активированный `venv`), не полагайся на системный Python.
22. Любые тесты (`pytest`, локальные smoke-скрипты handlers, интеграционные прогоны) запускай только с повышенными правами после явного запроса пользователю.

- убедись, что у пользователя нет незакоммиченных изменений (или явно подтвердил, что их можно включить в релиз);
- синхронизируй `dev` с `origin/dev` и убедись, что актуальные изменения в `dev` запушены;
- не переключайся в `main` и не выполняй операций в этой ветке: доступ к `main` запрещен для AI-агента (merge в `main` выполняется владельцем вручную вне задач агента);
- повысь `__version__` в `src/__init__.py` по схеме `major.minor.patch`, где каждое число 0..9:
  - если `patch < 9`: `patch += 1`;
  - если `patch == 9`: `patch = 0`, `minor += 1`;
  - если `minor == 9` и был перенос: `minor = 0`, `major += 1`;
- обнови `RELEASE_NOTES.md` по выполненным задачам текущего релиза;
- выполни релизную чистку `IMPROVEMENTS.md` только после переноса этих задач в `RELEASE_NOTES.md`;
- проверь синхронизацию через `python scripts/release_sync.py --tag vX.Y.Z` (при необходимости `--write`);
- сделай финальный commit релиза (version + release notes + cleanup backlog);
- создай tag формата `vX.Y.Z` на финальном commit и обеспечь соответствие `__version__ == X.Y.Z`;
- после этого передай пользователю изменения на финальный push ветки и тега.

Дополнительные рабочие правила:

- Начинай анализ с `src/main.py`, `src/config.py`, `src/bot/processing/*`, `src/handlers/manager.py`, `src/middlewares/db/*`.
- При расхождении документации и кода выбирай код и обновляй этот файл.
- Новые найденные проблемы добавляй в `Known Issues / Gaps` этого файла.
- Не подключай новые handlers в runtime (например, Yandex Music) без явной проверки end-to-end и env-требований.

## Next Recommended Steps

1. Определить политику прав доступа к командам переключения (`/toggle_*`, `/start`, `/stop`), если текущее поведение нужно ужесточить.
2. Явно решить судьбу оставшихся отключенных handlers (Yandex Music: подключение или архивирование).
3. При необходимости добавить webhook-режим.
