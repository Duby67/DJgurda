# Deploy Layout

## Схема расположения файлов (сервер и контейнер)

Ниже схема основана на фактических путях из:

- `src/config.py`
- `src/middlewares/db/core.py`
- `src/bot/lifespan/startup.py`
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
   │  │  └─ bot.db                 # SQLite база
   │  └─ cookies/
   │     └─ youtube_cookies.txt    # cookies для YouTube
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
│     ├─ db/                       # volume mount с сервера
│     │  └─ bot.db
│     ├─ cookies/                  # volume mount (read-only)
│     │  └─ youtube_cookies.txt
│     └─ temp_files/               # временные файлы внутри контейнера
└─ logs/                           # volume mount с сервера
```

## Проброс volume (из `manager.sh`)

```text
<server>/data/db      -> /app/src/data/db
<server>/data/cookies -> /app/src/data/cookies:ro
<server>/data/temp_files -> /app/src/data/temp_files
<server>/logs         -> /app/logs
```

## Какие модули используют эти пути

- `BOT_DB_PATH`:
  - читается в `src/config.py`
  - используется для SQLAlchemy URL в `src/middlewares/db/core.py`
- `YOUTUBE_COOKIES_PATH`:
  - валидируется в `src/config.py` (файл должен существовать)
- `PROJECT_TEMP_DIR` (`/app/src/data/temp_files` в контейнере):
  - формируется в `src/config.py`
  - используется миксинами `src/handlers/mixins/*` для скачивания временных файлов
  - очищается на startup в `src/bot/lifespan/startup.py`

## Стадии деплоя в `manager.sh`

`manager.sh` общий для `dev` и `prod`.  
Любые изменения скрипта должны сохранять рабочий перезапуск обоих окружений, даже если `prod` временно отстает от `dev`.

Скрипт выполняет деплой в фиксированном порядке с логами по шагам:

1. `acquire-lock`:
   - ожидание глобального lock-файла (`$HOME/.cache/djgurda/deploy.lock`);
   - предотвращает параллельный деплой из cron/CI/manual для dev/prod.
2. `preflight`:
   - проверка `docker` в `PATH`;
   - проверка `flock` и доступности docker daemon;
   - проверка каталога окружения и `.env`;
   - проверка freeze-файлов:
     - глобальный: `$HOME/.bot_deploy.freeze`;
     - окружения: `$HOME/bot_{env}/.deploy.freeze`;
   - проверка обязательных ключей;
   - проверка ожидаемых контейнерных путей (`BOT_DB_PATH`, `YOUTUBE_COOKIES_PATH`).
3. `prepare-runtime`:
   - создание runtime-директорий (`db`, `cookies`, `logs`);
   - проверка/создание `youtube_cookies.txt`.
4. `stop-container`:
   - остановка и удаление контейнера целевого окружения.
5. `cleanup-cache`:
   - очистка локального кэша деплой-каталога;
   - `docker system prune -f`.
6. `start-container`:
   - запуск контейнера с нужным образом, томами и restart policy;
   - проверка факта старта контейнера через `docker ps`.
7. `summary`:
   - итоговая сводка с окружением, контейнером, образом, лог-файлом и длительностью.
