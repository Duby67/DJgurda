# Deploy Layout

## РЎС…РµРјР° СЂР°СЃРїРѕР»РѕР¶РµРЅРёСЏ С„Р°Р№Р»РѕРІ (СЃРµСЂРІРµСЂ Рё РєРѕРЅС‚РµР№РЅРµСЂ)

РќРёР¶Рµ СЃС…РµРјР° РѕСЃРЅРѕРІР°РЅР° РЅР° С„Р°РєС‚РёС‡РµСЃРєРѕРј runtime-РєРѕРґРµ:

- `src/config.py`
- `src/utils/runtime_storage.py`
- `src/bot/lifespan/startup.py`
- `src/bot/lifespan/shutdown.py`
- `src/middlewares/db/core.py`
- `.github/workflows/deploy-*.yml`
- `manager.sh`

## РЎРµСЂРІРµСЂ (VPS)

Р”Р»СЏ `dev`:

```text
/home/<SSH_USER>/
в”њв”Ђ manager.sh
в””в”Ђ bot_dev/
   в”њв”Ђ .env
   в”њв”Ђ data/
   в”‚  в”њв”Ђ db/
   в”‚  в”‚  в””в”Ђ bot.db                  # РІРЅРµС€РЅСЏСЏ SQLite Р±Р°Р·Р°
   в”‚  в””в”Ђ cookies/
   в”‚     в”њв”Ђ www.youtube.com_cookies.txt     # РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ
   в”‚     в”њв”Ђ instagram_cookies.txt   # РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ
   в”‚     в””в”Ђ vk.com_cookies.txt      # РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ
   в””в”Ђ logs/
```

Р”Р»СЏ `prod` Р°РЅР°Р»РѕРіРёС‡РЅРѕ:

```text
/home/<SSH_USER>/bot_prod/...
```

## Docker РєРѕРЅС‚РµР№РЅРµСЂ

```text
/app
в”њв”Ђ src/
в”‚  в””в”Ђ data/
в”‚     в”њв”Ђ db/                        # volume mount СЃ СЃРµСЂРІРµСЂР°
в”‚     в”‚  в””в”Ђ bot.db
в”‚     в””в”Ђ cookies/                   # volume mount (read-only)
в”‚        в”њв”Ђ www.youtube.com_cookies.txt
в”‚        в”њв”Ђ instagram_cookies.txt
в”‚        в””в”Ђ vk.com_cookies.txt
в””в”Ђ logs/                            # volume mount СЃ СЃРµСЂРІРµСЂР°
```

Р’СЂРµРјРµРЅРЅС‹Рµ С„Р°Р№Р»С‹ РІ РєРѕРЅС‚РµР№РЅРµСЂРµ С…СЂР°РЅСЏС‚СЃСЏ РІРЅРµ `/app/src/data`:

```text
/tmp/djgurda/temp_files/            # Р·РЅР°С‡РµРЅРёРµ BOT_TEMP_DIR РІ deploy
в”њв”Ђ TikTokHandler/
в”њв”Ђ YouTubeHandler/
в”њв”Ђ InstagramHandler/
в”њв”Ђ CoubHandler/
в””в”Ђ VKHandler/
```

## РџСЂРѕР±СЂРѕСЃ volumes (РёР· `manager.sh`)

```text
<server>/data/db      -> /app/src/data/db
<server>/data/cookies -> /app/src/data/cookies:ro
<server>/logs         -> /app/logs
```

`temp_files` volume Р±РѕР»СЊС€Рµ РЅРµ РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ.

## РљРѕРЅС‚СЂР°РєС‚ env РїСѓС‚РµР№

- `BOT_DB_PATH=/app/src/data/db/bot.db` (РѕР±СЏР·Р°С‚РµР»СЊРЅС‹Р№)
- `COOKIES_DIR=/app/src/data/cookies` (СЂРµРєРѕРјРµРЅРґСѓРµРјС‹Р№)
- `BOT_TEMP_DIR=/tmp/djgurda/temp_files` (РІ deploy Р·Р°РґР°РµС‚СЃСЏ workflow)
- `*_COOKIES_PATH` РѕРїС†РёРѕРЅР°Р»СЊРЅС‹ РєР°Рє СЏРІРЅС‹Р№ override:
  - `YOUTUBE_COOKIES_PATH`
  - `INSTAGRAM_COOKIES_PATH`
  - `VK_COOKIES_PATH`

## РљР°Рє runtime РёСЃРїРѕР»СЊР·СѓРµС‚ РїСѓС‚Рё

- Р‘Р”:
  - С‡РёС‚Р°РµС‚СЃСЏ РІ `src/config.py` (`DB_FILE`);
  - РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ РІ SQLAlchemy URL РІ `src/middlewares/db/core.py`.

- Cookies:
  - РїСЂРёРѕСЂРёС‚РµС‚ Сѓ СЏРІРЅС‹С… `*_COOKIES_PATH`;
  - РµСЃР»Рё `*_COOKIES_PATH` РїСѓСЃС‚, Р±РµСЂРµС‚СЃСЏ `<COOKIES_DIR>/<provider_file>`;
  - РїСЂРѕРІР°Р№РґРµСЂРЅС‹Рµ С„Р°Р№Р»С‹: `www.youtube.com_cookies.txt`, `instagram_cookies.txt`, `vk.com_cookies.txt`;
  - РїСѓСЃС‚С‹Рµ/Р·Р°РіР»СѓС€РµС‡РЅС‹Рµ cookies-С„Р°Р№Р»С‹ РёРіРЅРѕСЂРёСЂСѓСЋС‚СЃСЏ СЃРѕРѕС‚РІРµС‚СЃС‚РІСѓСЋС‰РёРјРё handler-СѓС‚РёР»РёС‚Р°РјРё.

- Temp runtime storage:
  - `ensure_runtime_storage(...)` РЅР° startup СЃРѕР·РґР°РµС‚:
    - СЂРѕРґРёС‚РµР»СЊСЃРєСѓСЋ РґРёСЂРµРєС‚РѕСЂРёСЋ Р‘Р”;
    - `BOT_TEMP_DIR`;
    - РїРѕРґРїР°РїРєРё РїРѕ Р°РєС‚РёРІРЅС‹Рј handler-РєР»Р°СЃСЃР°Рј;
  - `cleanup_expired_temp_files(MAX_AGE_SECONDS)` РЅР° startup СѓРґР°Р»СЏРµС‚ СѓСЃС‚Р°СЂРµРІС€РёРµ РІСЂРµРјРµРЅРЅС‹Рµ С„Р°Р№Р»С‹;
  - `cleanup_all_temp_files()` РЅР° shutdown СѓРґР°Р»СЏРµС‚ РІСЃРµ РІСЂРµРјРµРЅРЅС‹Рµ С„Р°Р№Р»С‹.

## РЎС‚Р°РґРёРё РґРµРїР»РѕСЏ РІ `manager.sh`

`manager.sh` РѕР±С‰РёР№ РґР»СЏ `dev` Рё `prod`.

РЎРєСЂРёРїС‚ РІС‹РїРѕР»РЅСЏРµС‚ РґРµРїР»РѕР№ РІ С„РёРєСЃРёСЂРѕРІР°РЅРЅРѕРј РїРѕСЂСЏРґРєРµ:

1. `acquire-lock`:
   - Р·Р°С…РІР°С‚ РіР»РѕР±Р°Р»СЊРЅРѕРіРѕ lock-С„Р°Р№Р»Р° (`$HOME/.cache/djgurda/deploy.lock`).
2. `preflight`:
   - РїСЂРѕРІРµСЂРєРё `docker`, `flock`, РґРѕСЃС‚СѓРїРЅРѕСЃС‚Рё daemon;
   - РїСЂРѕРІРµСЂРєРё РѕРєСЂСѓР¶РµРЅРёСЏ, `.env` Рё freeze-С„Р°Р№Р»РѕРІ;
   - РїСЂРѕРІРµСЂРєР° РѕР±СЏР·Р°С‚РµР»СЊРЅС‹С… env-РєР»СЋС‡РµР№ Рё `BOT_DB_PATH`.
3. `prepare-runtime`:
   - СЃРѕР·РґР°РЅРёРµ СЃРµСЂРІРµСЂРЅС‹С… РґРёСЂРµРєС‚РѕСЂРёР№ `db`, `cookies`, `logs`.
4. `stop-container`:
   - graceful-РѕСЃС‚Р°РЅРѕРІРєР° (`docker stop --time 25`) Рё СѓРґР°Р»РµРЅРёРµ РєРѕРЅС‚РµР№РЅРµСЂР°.
5. `cleanup-cache`:
   - РѕС‡РёСЃС‚РєР° `.cache` + `docker system prune -f`.
6. `start-container`:
   - `docker run` СЃ volume РґР»СЏ `db/cookies/logs`;
   - РїСЂРѕРІРµСЂРєР°, С‡С‚Рѕ РєРѕРЅС‚РµР№РЅРµСЂ Р·Р°РїСѓС‰РµРЅ.
7. `summary`:
   - РёС‚РѕРіРѕРІР°СЏ СЃРІРѕРґРєР° РїРѕ РґРµРїР»РѕСЋ.

