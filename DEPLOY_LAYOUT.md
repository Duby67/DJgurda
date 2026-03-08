# Deploy Layout

## Схема расположения файлов (сервер и контейнер)

Ниже схема основана на фактическом runtime-коде:

- `src/config.py`
- `src/utils/runtime_storage.py`
- `src/bot/lifespan/startup.py`
- `src/bot/lifespan/shutdown.py`
- `src/middlewares/db/core.py`
- `.github/workflows/deploy-*.yml`
- `manager.sh`

## Сервер (VPS)

Для `dev`:

```text
/home/<SSH_USER>/
├─ manager.sh
└─ bot_dev/
   ├─ .env
   ├─ data/
   │  ├─ db/
   │  │  └─ bot.db                  # внешняя SQLite база
   │  └─ cookies/
   │     ├─ youtube_cookies.txt     # опционально
   │     ├─ instagram_cookies.txt   # опционально
   │     └─ vk.com_cookies.txt      # опционально
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
│        ├─ youtube_cookies.txt
│        ├─ instagram_cookies.txt
│        └─ vk.com_cookies.txt
└─ logs/                            # volume mount с сервера
```

Временные файлы в контейнере хранятся вне `/app/src/data`:

```text
/tmp/djgurda/temp_files/            # значение BOT_TEMP_DIR в deploy
├─ TikTokHandler/
├─ YouTubeHandler/
├─ InstagramHandler/
├─ CoubHandler/
└─ VKHandler/
```

## Проброс volumes (из `manager.sh`)

```text
<server>/data/db      -> /app/src/data/db
<server>/data/cookies -> /app/src/data/cookies:ro
<server>/logs         -> /app/logs
```

`temp_files` volume больше не используется.

## Контракт env путей

- `BOT_DB_PATH=/app/src/data/db/bot.db` (обязательный)
- `COOKIES_DIR=/app/src/data/cookies` (рекомендуемый)
- `BOT_TEMP_DIR=/tmp/djgurda/temp_files` (в deploy задается workflow)
- `*_COOKIES_PATH` опциональны как явный override:
  - `YOUTUBE_COOKIES_PATH`
  - `INSTAGRAM_COOKIES_PATH`
  - `VK_COOKIES_PATH`

## Как runtime использует пути

- БД:
  - читается в `src/config.py` (`DB_FILE`);
  - используется в SQLAlchemy URL в `src/middlewares/db/core.py`.

- Cookies:
  - приоритет у явных `*_COOKIES_PATH`;
  - если `*_COOKIES_PATH` пуст, берется `<COOKIES_DIR>/<provider_file>`;
  - провайдерные файлы: `youtube_cookies.txt`, `instagram_cookies.txt`, `vk.com_cookies.txt`;
  - пустые/заглушечные cookies-файлы игнорируются соответствующими handler-утилитами.

- Temp runtime storage:
  - `ensure_runtime_storage(...)` на startup создает:
    - родительскую директорию БД;
    - `BOT_TEMP_DIR`;
    - подпапки по активным handler-классам;
  - `cleanup_expired_temp_files(MAX_AGE_SECONDS)` на startup удаляет устаревшие временные файлы;
  - `cleanup_all_temp_files()` на shutdown удаляет все временные файлы.

## Стадии деплоя в `manager.sh`

`manager.sh` общий для `dev` и `prod`.

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
