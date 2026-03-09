# Deploy Layout

Этот файл поддерживается как deploy-документ проекта и хранится в `docs/`.

## Схема расположения файлов (сервер и контейнер)

Ниже схема основана на фактическом runtime-коде:

- `src/config.py`
- `src/utils/runtime_storage.py`
- `src/bot/lifespan/startup.py`
- `src/bot/lifespan/shutdown.py`
- `src/middlewares/db/core.py`
- `.github/workflows/deploy-*.yml`
- `deploy/Dockerfile`
- `deploy/Dockerfile.dockerignore`
- `deploy/manager.sh`

## Сервер (VPS)

Для `dev`:

```text
/home/<SSH_USER>/
├─ deploy/
│  ├─ manager.sh
│  ├─ sync_cookies.sh
│  ├─ sync_cookies.bat
│  ├─ sync_cookies.env.example
│  └─ cookies/       # materialized on runner
│     ├─ .gitkeep
│     ├─ coub_cookies.txt
│     ├─ instagram_cookies.txt
│     ├─ tiktok_cookies.txt
│     ├─ vk.com_cookies.txt
│     └─ www.youtube.com_cookies.txt 
└─ bot_dev/
   ├─ .env
   ├─ data/
   │  ├─ db/
   │  │  └─ bot.db                  # внешняя SQLite база
   │  └─ cookies/
   │     ├─ instagram_cookies.txt
   │     ├─ tiktok_cookies.txt
   │     ├─ vk.com_cookies.txt
   │     └─ www.youtube.com_cookies.txt
   └─ logs/
```

Для `prod` аналогично:

```text
/home/<SSH_USER>/bot_prod/...
```

## Docker контейнер

```text
/app
├─ src/
│  └─ data/
│     ├─ db/                        # volume mount с сервера
│     │  └─ bot.db
│     └─ cookies/                   # volume mount (read-only)
│        ├─ instagram_cookies.txt
│        ├─ tiktok_cookies.txt
│        ├─ vk.com_cookies.txt
│        └─ www.youtube.com_cookies.txt
└─ logs/                            # volume mount с сервера
```

Временные файлы в контейнере хранятся в фиксированной runtime-директории:

```text
/app/src/data/runtime/
├─ TikTokHandler/
├─ YouTubeHandler/
├─ InstagramHandler/
├─ CoubHandler/
└─ VKHandler/
```

## Проброс volumes (из `deploy/manager.sh`)

```text
<server>/data/db      -> /app/src/data/db
<server>/data/cookies -> /app/src/data/cookies:ro
<server>/logs         -> /app/logs
```

`runtime` volume больше не используется.

## Логика cookie-директорий

- `src/data/cookies`
  - runtime-оригиналы, с которыми бот взаимодействует в текущем окружении;
  - в deploy директория приходит с сервера как read-only volume.
- `local/cookies`
  - локальные оригиналы cookies для smoke-проверок и ручных тестов;
  - локальные smoke-тесты копируют их в `src/data/cookies`.
- `deploy/cookies`
  - deploy-источник cookies;
  - в git хранится только `.gitkeep`, реальные `*_cookies.txt` игнорируются;
  - GitHub Actions materializes эту директорию из опциональных secrets, затем синхронизирует только переданные файлы на сервер с перезаписью по совпадающим именам;
  - если secrets не заданы, deploy продолжает использовать существующие cookies на сервере.
- `deploy/sync_cookies.sh`, `deploy/sync_cookies.bat`
  - ручная синхронизация cookies для deploy-контура;
  - скрипты только добавляют новые `*_cookies.txt` на сервер или перезаписывают одноименные, но не удаляют файлы, которых нет локально.
- `deploy/sync_cookies.env`
  - локальный конфиг ручной синхронизации с `REMOTE_USER`, `REMOTE_HOST`, `REMOTE_PORT`;
  - не попадает в git.
- `deploy/sync_cookies.env.example`
  - шаблон локального конфига ручной синхронизации.

## Контракт env путей

- `BOT_DB_PATH=/app/src/data/db/bot.db` (обязательный)
- `COOKIES_DIR=/app/src/data/cookies` (рекомендуемый)
- `*_COOKIES_PATH` опциональны как явный override:
  - `YOUTUBE_COOKIES_PATH`
  - `INSTAGRAM_COOKIES_PATH`
  - `TIKTOK_COOKIES_PATH`
  - `VK_COOKIES_PATH`

## Как runtime использует пути

- БД:
  - читается в `src/config.py` (`DB_FILE`);
  - используется в SQLAlchemy URL в `src/middlewares/db/core.py`.

- Cookies:
  - приоритет у явных `*_COOKIES_PATH`;
  - если `*_COOKIES_PATH` пуст, берется `<COOKIES_DIR>/<provider_file>`;
  - провайдерные файлы: `www.youtube.com_cookies.txt`, `instagram_cookies.txt`, `tiktok_cookies.txt`, `vk.com_cookies.txt`;
  - пустые/заглушечные cookies-файлы игнорируются соответствующими handler-утилитами.

- Temp runtime storage:
  - `ensure_runtime_storage(...)` на startup создает:
    - родительскую директорию БД;
    - `/app/src/data/runtime`;
    - подпапки по активным handler-классам;
  - `cleanup_expired_runtime(MAX_AGE_SECONDS)` на startup удаляет устаревшие временные файлы;
  - `cleanup_all_runtime()` на shutdown удаляет все временные файлы.

## Стадии деплоя в `deploy/manager.sh`

`deploy/manager.sh` общий для `dev` и `prod`.

Скрипт выполняет деплой в фиксированном порядке:

1. `acquire-lock`:
   - захват глобального lock-файла (`$HOME/.cache/djgurda/deploy.lock`).
2. `preflight`:
   - проверки `docker`, `flock`, доступности daemon;
   - проверки окружения, `.env` и freeze-файлов;
   - проверка обязательных env-ключей и `BOT_DB_PATH`.
3. `prepare-runtime`:
   - создание серверных директорий `db`, `cookies`, `logs`.
4. `stop-container`:
   - graceful-остановка (`docker stop --time 25`) и удаление контейнера.
5. `cleanup-cache`:
   - очистка `.cache` + `docker system prune -f`.
6. `start-container`:
   - `docker run` с volume для `db/cookies/logs`;
   - проверка, что контейнер запущен.
7. `summary`:
   - итоговая сводка по деплою.

## Дополнительные шаги GitHub Actions до `deploy/manager.sh`

1. Workflow materializes `deploy/cookies` на runner из secrets:
   - `YOUTUBE_COOKIES_FILE`
   - `INSTAGRAM_COOKIES_FILE`
   - `TIKTOK_COOKIES_FILE`
   - `VK_COOKIES_FILE`
   - `COUB_COOKIES_FILE`
2. Workflow очищает только staging-папку `/home/<SSH_USER>/deploy/cookies` от старых `*_cookies.txt`.
3. `deploy/cookies` копируется на сервер в `/home/<SSH_USER>/deploy/cookies`.
4. Если в staging есть `*_cookies.txt`, workflow копирует их в `/home/<SSH_USER>/bot_{env}/data/cookies` с перезаписью только одноименных файлов.
5. Если после materialize в `deploy/cookies` нет ни одного `*_cookies.txt`, deploy не завершается ошибкой и контейнер продолжает использовать уже существующие cookies на сервере.
