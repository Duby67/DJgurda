# DJgurda Bot

Асинхронный Telegram-бот для обработки медиа-ссылок в чатах.  
Текущий рабочий контур ориентирован на TikTok (видео, фото/слайдшоу, профили), с сохранением статистики по чатам и пользователям.

## Главный контекст проекта
Основной источник контекста для разработчиков и AI-агентов:
- [`.github/ai_context.md`](./.github/ai_context.md)

Политика актуальности:
- `README.md` и `.github/ai_context.md` - канонические документы.
- Контекст всегда проверяется по коду в `src/`.

## Важный статус по структуре
- `docs/` не используется как поддерживаемый источник актуального контекста.
- `tests/` / `test/` на текущем этапе не считаются активной частью проекта и не являются источником истины.
- При возврате к этим областям в будущем их нужно явно заново договорить и обновить в `.github/ai_context.md`.

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
```

3. Настройка `.env` (обязательные переменные валидируются в `src/config.py`):
- `BOT_DB_PATH`
- `BOT_VERSION`
- `ADMIN_ID`
- `BOT_TOKEN`
- `YANDEX_MUSIC_TOKEN`
- `YOUTUBE_COOKIES_PATH`

Шаблон:
- `env.example` (скопируй в `.env` и подставь значения).

Для Docker/deploy используются значения путей внутри контейнера:
- `BOT_DB_PATH=/app/src/data/db/bot.db`
- `YOUTUBE_COOKIES_PATH=/app/src/data/cookies/youtube_cookies.txt`

4. Старт:
```bash
python -m src.main
```

## Точки входа и ключевые файлы
- `src/main.py` - старт приложения.
- `src/config.py` - env-конфигурация и лимиты.
- `src/bot/processing/media_router.py` - вход в поток обработки ссылок.
- `src/handlers/manager.py` - выбор обработчика по URL.
- `src/middlewares/db/*` - модели, миграции и DB-операции.
- `.github/workflows/*` и `manager.sh` - CI/CD и деплой.

## Схема расположения файлов (сервер и контейнер)
Подробная схема вынесена в отдельный файл:
- [`DEPLOY_LAYOUT.md`](./DEPLOY_LAYOUT.md)

## Текущее ограничение
В runtime зарегистрирован только `TikTokHandler`.  
Другие handlers присутствуют в коде, но не подключены в `ServiceManager`.

## Управление в чатах
- Команды `/start` и `/stop` разрешены для всех участников чата.
- Эти команды влияют только на флаг работы бота в текущем чате и не затрагивают другие чаты.
