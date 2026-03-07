# AI Context

## Project Summary

DJgurda Bot - асинхронный Telegram-бот для групповых чатов.  
Основной сценарий: пользователь отправляет ссылку на медиа-контент, бот извлекает/загружает контент и публикует его в унифицированном виде в чат. Целевая аудитория - участники Telegram-чатов, где нужны быстрые репосты контента из внешних платформ.

- Продуктовое допущение: приоритетный сценарий использования - через мобильные устройства (телефоны), поэтому UX ответов и медиа ориентирован на мобильный Telegram-клиент.

## Current Status

- Реализован рабочий pipeline на `aiogram 3.x` в polling-режиме.
- Активные обработчики в runtime: TikTok, YouTube, Instagram (`ServiceManager` регистрирует `TikTokHandler`, `YouTubeHandler`, `InstagramHandler`).
- Обработчики Yandex Music / VK присутствуют в коде, но сейчас отключены в менеджере.
- Есть SQLite-хранилище настроек чатов и статистики через async SQLAlchemy.
- CI/CD разворачивает Docker-образ в dev/prod окружения через GitHub Actions + SSH.
- Команды `/start` и `/stop` разрешены всем участникам чата; они меняют состояние бота только в текущем чате.
- При `bot_enabled=false` обработка сообщений в чате блокируется, кроме `/start`, `/stop`, `/toggle_bot`.
- `docs/` не используются как поддерживаемые источники контекста на текущем этапе.
- `tests/` и `test/` в основном остаются legacy-зоной контекста, кроме согласованных локальных smoke-скриптов handlers:
  - `test/handlers/TikTok/test_tiktok_handlers_local.py` + `test/handlers/TikTok/TikTok_urls.py`
  - `test/handlers/YouTube/test_youtube_handlers_local.py` + `test/handlers/YouTube/YouTube_urls.py`
  - `test/handlers/Instagram/test_instagram_handlers_local.py` + `test/handlers/Instagram/Instagram_urls.py`

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
- `src/data/` - runtime-данные (`db`, `temp_files`, `cookies`).
- `manager.sh` - серверный запуск контейнера после деплоя.
  - `manager.sh` общий для `dev` и `prod`; изменения в нем должны оставаться совместимыми с перезапуском обоих окружений.
  - учитывать, что `prod` может временно отставать от `dev`.

## Entrypoints

- Локальный запуск:
  - `python -m src.main`
- Runtime режим:
  - Polling через `Dispatcher.start_polling(...)`.
- Жизненный цикл:
  - startup: DB init, очистка temp, уведомления о запуске.
  - shutdown: уведомления, закрытие DB.
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
- `YOUTUBE_COOKIES_PATH`

Примечания по окружению:

- Эталон переменных окружения для разработки/проверок: `env.example`.
- Персональный `local/.env` не является частью проекта и не используется как источник истины.
- Локальная ОС разработки: Windows 11.
- Целевая ОС runtime: Ubuntu 24; возможны отличия поведения из-за различий ОС и shell-инструментов.

Опциональные:

- Явно не выделены в `src/config.py`; отсутствие значений выше приводит к ошибке старта.

## Run & Development

Минимальный локальный контур:

1. Python 3.11+
2. FFmpeg в `PATH`
3. `pip install -r requirements.txt`
4. заполнить `.env`
5. `python -m src.main`

Примечания:

- В текущей политике проекта `tests/`/`test/` в целом не считаются поддерживаемой частью контекста и не являются обязательным шагом онбординга.
- Исключение для практической проверки handlers: используй локальные smoke-скрипты в `test/handlers/TikTok`, `test/handlers/YouTube`, `test/handlers/Instagram`.
- Правило и пример структуры будущих smoke-тестов handlers зафиксированы в `README.md` (секция `Правило Для Handler Smoke-Тестов`).
- Docker-запуск поддерживается через `Dockerfile`; `docker-compose.yml` сейчас отсутствует.

## Integrations

- Telegram API: `aiogram`.
- База данных: SQLite (`aiosqlite` + SQLAlchemy async ORM).
- Внешние медиа-источники: через `yt-dlp` и конкретные handlers.
- Yandex Music: SDK подключен в коде handler, но handler в runtime отключен.
- URL resolving: `aiohttp` (HEAD/GET redirects).
- Deployment: GitHub Actions + GHCR + SSH deploy script (`manager.sh`).
- В deploy workflows пути `BOT_DB_PATH` и `YOUTUBE_COOKIES_PATH` задаются явно в `.env` на сервере (без GitHub secrets).

## Known Issues / Gaps

- В runtime пока не подключены Yandex Music и VK handlers.
- `docker-compose.yml` отсутствует, хотя упоминался в старых описаниях.
- В текущем `.env` может отсутствовать `BOT_DB_PATH`; это ломает старт.
- Нет явного контроля прав для команд управления состоянием бота в чатах.
- Webhook-режим не реализован.

## Legacy / Ignored Areas

- `docs/` - legacy зона; не используется как источник актуальной информации.
- `tests/` / `test/` - legacy зона на текущем этапе; не используется как источник актуального контекста, кроме согласованных smoke-скриптов handlers в `test/handlers/TikTok`, `test/handlers/YouTube`, `test/handlers/Instagram`.
- `venv/`, `__pycache__/`, `.env` - локальные артефакты окружения; не считать источником проектной правды даже если они присутствуют в рабочей директории.
- Старые markdown-артефакты вне `README.md` и `.github/ai_context.md` считать вторичными/историческими, если они не синхронизированы с кодом.

## Instructions for AI Agents

1. Перед началом правок убедись, что активна ветка `dev`.
2. Сначала читай `README.md` и `.github/ai_context.md`.
3. При любом обращении к `README.md` обязательно дополнительно проверяй `IMPROVEMENTS.md`.
4. Перед внесением любых правок в код обязательно сверяйся с `IMPROVEMENTS.md`; если планируемые или уже выполненные изменения там не отражены, добавь их в backlog и только после этого продолжай работу.
5. Затем сверяй контекст по реальному коду.
6. Больше доверяй коду и config-файлам, чем старым markdown-документам.
7. Не считай `docs/` и `tests/` актуальным источником правды, кроме согласованных smoke-скриптов проверки handlers (`test/handlers/TikTok`, `test/handlers/YouTube`, `test/handlers/Instagram`).
8. Не анализируй `venv/`, `__pycache__/` и `.env` как источник контекста проекта.
9. Не выдумывай отсутствующие фичи.
10. Если что-то непонятно - фиксируй это в разделе gaps, а не домысливай.
11. Вноси изменения минимально и локально, не ломая существующую структуру.
12. Язык комментариев и всех человеко-читаемых проектных файлов - русский.
13. Логи, технические runtime-сообщения и похожие служебные сегменты - английский.
14. В конце обработки, после завершения всех правок, предлагай commit message на английском в формате готовой команды для cmd/PowerShell, например:git commit -a -m "docs: update release workflow and backlog sync".
15. Все выполненные задачи обязательно сверяй с `IMPROVEMENTS.md` и обновляй там статус; при релизной чистке выполненные задачи удаляй из активного backlog.
16. Для релизов с tag используй `python scripts/release_sync.py --tag <tag>` (и `--write` при необходимости обновить шаблоны файлов).
17. При запросе на выпуск новой версии действуй по процедуре:
18. При изменении `.md` файлов соблюдай единый стиль markdownlint: ориентируйся на `.markdownlint.json`, исключения из `.markdownlintignore` и перед финализацией проверяй `npx.cmd markdownlint-cli2 "**/*.md" ".github/*.md"`.
19. В пользовательских caption удаляй хэштеги из заголовков; если после очистки заголовок пустой, используй нейтральный fallback-текст вместо исходного набора хэштегов.
20. Если важный скрипт/тулза не запускается из-за ограничений среды (sandbox, права, сеть), запрашивай повышение прав у пользователя вместо молчаливого пропуска шага.

- убедись, что у пользователя нет незакоммиченных изменений (или явно подтвердил, что их можно включить в релиз);
- синхронизируй `dev` с `origin/dev` и убедись, что актуальные изменения в `dev` запушены;
- перейди в `main` и выполни merge `dev` для получения актуального состояния репозитория;
- повысь `__version__` в `src/__init__.py` по схеме `major.minor.patch`, где каждое число 0..9:
  - если `patch < 9`: `patch += 1`;
  - если `patch == 9`: `patch = 0`, `minor += 1`;
  - если `minor == 9` и был перенос: `minor = 0`, `major += 1`;
- создай tag формата `vX.Y.Z` и обеспечь соответствие `__version__ == X.Y.Z`;
- обнови `RELEASE_NOTES.md` по выполненным задачам;
- удали выполненные задачи из активного backlog `IMPROVEMENTS.md`;
- после этого передай пользователю изменения на финальный commit/push.

Дополнительные рабочие правила:

- Начинай анализ с `src/main.py`, `src/config.py`, `src/bot/processing/*`, `src/handlers/manager.py`, `src/middlewares/db/*`.
- При расхождении документации и кода выбирай код и обновляй этот файл.
- Новые найденные проблемы добавляй в `Known Issues / Gaps` этого файла.
- Не подключай новые handlers в runtime (например, Yandex Music / VK) без явной проверки end-to-end и env-требований.

## Next Recommended Steps

1. Определить политику прав доступа к командам переключения (`/toggle_*`, `/start`, `/stop`), если текущее поведение нужно ужесточить.
2. Явно решить судьбу оставшихся отключенных handlers (Yandex Music / VK: подключение или архивирование).
3. При необходимости добавить webhook-режим.
