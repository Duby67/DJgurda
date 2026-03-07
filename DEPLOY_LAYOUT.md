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
Скрипт выполняет деплой в фиксированном порядке с логами по шагам:
1. `preflight`:
   - проверка `docker` в `PATH`;
   - проверка каталога окружения и `.env`;
   - проверка обязательных ключей;
   - проверка ожидаемых контейнерных путей (`BOT_DB_PATH`, `YOUTUBE_COOKIES_PATH`).
2. `prepare-runtime`:
   - создание runtime-директорий (`db`, `cookies`, `logs`);
   - проверка/создание `youtube_cookies.txt`.
3. `stop-container`:
   - остановка и удаление контейнера целевого окружения.
4. `cleanup-cache`:
   - очистка локального кэша деплой-каталога;
   - `docker system prune -f`.
5. `start-container`:
   - запуск контейнера с нужным образом, томами и restart policy;
   - проверка факта старта контейнера через `docker ps`.
6. `summary`:
   - итоговая сводка с окружением, контейнером, образом, лог-файлом и длительностью.
