# Project Improvements

## Цель файла

Собрать практичные предложения по улучшению проекта DJgurda Bot, чтобы использовать их как технический backlog.

## Метаданные backlog

- Последняя ревизия backlog: 2026-03-08 | version/tag: v1.2.2

## Приоритет P0 (критично)

### 1. Безопасность секретов и локальных файлов

- Статус (2026-03-07): частично выполнено.
- Проблема: локальные секреты и служебные данные могут попадать в рабочий контекст.
- Действие:
  - Проверить `.gitignore` и исключить все чувствительные локальные артефакты. ✅ Выполнено.
  - Убедиться, что `.env` не содержит посторонних строк и хранит только env-переменные.
  - Ввести ротацию токенов при любом подозрении на утечку.
- Результат: снижение риска компрометации доступа к боту и инфраструктуре.

## Приоритет P1 (высокий)

### 2. Разграничение прав на команды управления

- Статус (2026-03-07): в работе (текущая политика зафиксирована, но может быть пересмотрена).
- Проблема: `/start` и `/stop` доступны всем участникам чата (сейчас это осознанно).  
  Проверка кода подтвердила, что при `bot_enabled=false` бот не обрабатывает другие сообщения и команды, кроме `/start`, `/stop`, `/toggle_bot` (через `BotEnabledMiddleware`).
- Действие:
  - Определить политику доступа: оставить как есть или ограничить администраторами.
  - Если ограничивать: добавить проверку роли через Telegram API.
- Результат: контроль над поведением бота в активных чатах.

### 3. Стратегия по неактивным handlers

- Статус (2026-03-08): частично выполнено.
- Проблема: в коде есть YouTube/Instagram/YandexMusic/VK handlers; после подключения YouTube/Instagram/VK в runtime остается неактивным YandexMusic.
- Действие:
  - Подключить готовые обработчики YouTube/Instagram в `ServiceManager` с минимальным риском для текущего TikTok pipeline. ✅ Выполнено.
  - Подключить `VKHandler` в `ServiceManager` с поддержкой `audio`/`playlist`, безопасными VK cookies и локальными smoke-проверками по шаблону `test/handlers/<Source>`. ✅ Выполнено (`src/handlers/resources/VK/*`, `src/handlers/manager.py`, `test/handlers/VK/*`, `src/config.py`, `env.example`).
  - Для VK Music стабилизировать extraction: использовать API-first цепочку `reload_audios`/`load_section`, декодировать `audio_api_unavailable`, поддержать HLS-загрузку трека и подтвердить локальным smoke-прогоном `4/4`. ✅ Выполнено (`src/handlers/resources/VK/VKHandler.py`, `test/handlers/VK/test_vk_handlers_local.py`).
  - Выбрать подход: поэтапное включение или архивирование оставшихся неиспользуемых обработчиков.
  - Для включаемых источников добавить критерии readiness и чеклист.
- Результат: меньше технического долга и понятный roadmap по источникам.

## Приоритет P2 (средний)

### 4. Улучшение конфигурационного контракта

- Статус (2026-03-08): в работе (частично выполнено).
- Проблема: `src/config.py` требует токены даже для неактивных интеграций.
- Действие:
  - Разделить обязательные и условно-обязательные env-переменные.
  - Для неактивных интеграций добавить lazy-проверки только при их использовании.
  - Синхронизировать `manager.sh` с runtime-контрактом YouTube cookies:
    - при `YOUTUBE_COOKIES_ENABLED=false` не требовать жестко `YOUTUBE_COOKIES_PATH` в preflight. ✅ Выполнено (`manager.sh`);
    - не создавать `youtube_cookies.txt` автоматически, если cookies выключены. ✅ Выполнено (`manager.sh`, `.github/workflows/deploy-dev.yml`, `.github/workflows/deploy-prod.yml`).
  - Добавить единый `COOKIES_DIR` и auto-discovery `youtube_cookies.txt` / `instagram_cookies.txt` / `vk.com_cookies.txt` при пустых `*_COOKIES_PATH`. ✅ Выполнено (`src/config.py`, `env.example`, `README.md`, `.github/ai_context.md`).
  - Перевести локальный источник оригинальных cookies в `local/cookies`, добавить автокопирование в `src/data/cookies` для smoke-тестов handlers и использовать для `yt-dlp` только временные рабочие копии cookie-файлов (без модификации оригиналов). ✅ Выполнено (`local/sync_cookies.cmd`, `test/handlers/_local_cookie_setup.py`, `test/handlers/*/test_*_handlers_local.py`, `src/handlers/resources/cookie_runtime.py`, `src/utils/cookies.py`, `README.md`, `.github/ai_context.md`, `env.example`).
  - В deploy отказаться от избыточной логики копирования cookies в workflow: создавать/монтировать `$HOME/bot_{env}/data/cookies` централизованно в `manager.sh`, содержимое папки управляется на сервере отдельно. ✅ Выполнено (`.github/workflows/deploy-dev.yml`, `.github/workflows/deploy-prod.yml`, `manager.sh`).
  - Убрать legacy-создание временных директорий из Docker/deploy и полагаться на runtime-проверки/создание директорий в Python-коде. ✅ Выполнено (`Dockerfile`, `manager.sh`, `src/handlers/mixins/base.py`).
  - Централизовать lifecycle runtime-хранилища: подготовка `BOT_TEMP_DIR` + per-handler temp-папок на startup, очистка устаревших временных файлов на startup и полная очистка temp на shutdown; хранить temp вне репозитория (по умолчанию системный temp-dir, в deploy `/tmp/djgurda/temp_files`). ✅ Выполнено (`src/config.py`, `src/utils/runtime_storage.py`, `src/bot/lifespan/startup.py`, `src/bot/lifespan/shutdown.py`, `src/handlers/manager.py`, `README.md`, `.github/ai_context.md`).
  - Унифицировать cookie-логику обработчиков: убрать дублирование `src/handlers/resources/{YouTube,Instagram,VK}/cookies.py`, вынести общий слой в `src/utils/cookies.py` (валидация/placeholder-check/runtime-copy/warn-once) и подключать его через базовый handler/mixin. Для VK оставить только специфичный парсинг cookies в dict для HTTP-запросов. ✅ Выполнено (`src/utils/cookies.py`, `src/handlers/mixins/base.py`, `src/handlers/resources/cookie_runtime.py`, удалены legacy-файлы `src/handlers/resources/{YouTube,Instagram,VK}/cookies.py`, `src/handlers/resources/YouTube/{YouTubeShorts.py,YouTubeChannel.py}`, `src/handlers/resources/Instagram/{InstagramHandler.py,InstagramReels.py,InstagramMediaGroup.py,InstagramStories.py,InstagramProfile.py}`, `src/handlers/resources/VK/VKHandler.py`, `test/handlers/Instagram/test_instagram_cookies_helpers.py`).
  - Уточнить нейтральный интерфейс cookies: выделить общий объект-обертку для исходного файла, создавать runtime-копии per request и использовать единый контракт в handlers/миксинах.
  - Добавить поддержку TikTok cookies по общей схеме (enabled/path + runtime-копии для yt-dlp).
  - Разнести VK-обработчики на отдельные mixin-классы `VKAudio` и `VKPlaylist`.
- Результат: проще локальный запуск и меньше ложных падений на старте.

### 5. Метрики пользовательской активности (пульс бота)

- Статус (2026-03-07): открыто.
- Проблема: сейчас нет продуктовой картины, как часто и кем используется бот.
- Действие:
  - Собирать DAU/WAU/MAU по `user_id` (по командам и обработкам ссылок).
  - Считать новых пользователей в день и долю returning users.
  - Считать активные чаты в день (`chat_id` с >=1 событием).
  - Собирать число входящих сообщений с URL и число успешно обработанных ссылок.
- Примеры графиков:
  - users per day
  - new users vs returning users
  - active chats per day
- Результат: понимание реального роста и удержания.

### 6. Метрики использования команд

- Статус (2026-03-07): открыто.
- Проблема: нет данных, какие команды реально полезны, а какие не используются.
- Действие:
  - Вести счетчик по командам:
    - `/start`, `/stop`, `/help`, `/info`, `/statistics`,
    - `/toggle_bot`, `/toggle_errors`, `/toggle_notifications`,
    - `/enable_errors`, `/disable_errors`, `/enable_notifications`, `/disable_notifications`.
  - Добавить метрику `command_error_rate` (ошибки / вызовы команды).
  - Выводить top commands и команды с нулевым использованием за период.
- Пример отчета:
  - `/start` 340
  - `/help` 120
  - `/statistics` 90
  - `/toggle_notifications` 15
- Результат: продуктовые решения по UX команд на основе данных.

### 7. Ошибки и отказоустойчивость

- Статус (2026-03-08): в работе (частично: закрыты задачи по TikTok/YouTube/Instagram и добавлен COUB video pipeline).
- Проблема: ошибки видны в логах, но нет агрегированной картины по типам и частоте.
- Действие:
  - Нормализовать TikTok URL перед обработкой: удалять трекинговые query-параметры (`_r`, `_t`), не затрагивая остальные параметры. ✅ Выполнено.
  - Устранить предупреждения валидатора GitHub Actions по неявным env-контекстам (`REPO_LC`, `OWNER_LC`) в deploy workflow через явные step outputs.
  - Для TikTok `media_group` добавить fallback-получение фото+аудио через альтернативный API (когда `yt-dlp` не отдает фото) и отправку в порядке: сначала аудио без caption, затем фото-альбом с caption. ✅ Выполнено.
  - Для TikTok `media_group` использовать музыкальные метаданные трека (title/performer) в аудио, а информацию о посте возвращать в caption альбома. ✅ Выполнено.
  - Для TikTok `media_group` при отправке аудио пробовать скачивать обложку трека из метаданных (`TikWM`/`yt-dlp`); если обложка недоступна или не скачалась, отправлять аудио без thumbnail. ✅ Выполнено.
  - В caption всегда удалять хэштеги из заголовка контента; если после очистки заголовок пустой, использовать нейтральный fallback-заголовок. ✅ Выполнено.
  - Для video-обработчиков добавить fallback повторной загрузки с `format=best`, если `yt-dlp` вернул `Requested format is not available`. ✅ Выполнено (`src/handlers/mixins/video.py`).
  - Для TikTok video расширить цепочку выбора форматов, чтобы не падать на узком фильтре `height/ext`. ✅ Выполнено (`src/handlers/resources/TikTok/TikTokVideo.py`).
  - Для `resolve_url` добавить распаковку interstitial URL (`consent.youtube.com`, `l.instagram.com`) с поддержкой абсолютных и относительных `continue/u` параметров. ✅ Выполнено (`src/utils/url.py`).
  - Универсализировать `_normalize_unwrapped_candidate`: относительные пути (`/path`) нормализуются через `fallback_origin` текущего interstitial-домена, без хардкода `youtube.com` внутри функции. ✅ Выполнено (`src/utils/url.py`).
  - Для YouTube cookies убрать безусловное использование `cookiefile`: включать только при `YOUTUBE_COOKIES_ENABLED=true`, а заглушечный/пустой файл автоматически игнорировать с диагностикой в логах. ✅ Выполнено (`src/utils/cookies.py`, `src/handlers/resources/YouTube/YouTubeShorts.py`, `src/handlers/resources/YouTube/YouTubeChannel.py`, `src/config.py`).
  - Для YouTube cookies вернуть безопасный auto-режим по умолчанию (`YOUTUBE_COOKIES_ENABLED=true`): валидный файл применяется автоматически, заглушка игнорируется, `false` отключает cookies принудительно. ✅ Выполнено (`src/config.py`, `src/utils/cookies.py`).
  - Для YouTube channel исправить расчет `🎬 Видео`: приоритет отдать `channel_video_count`/`video_count`, а `playlist_count` использовать только как fallback, чтобы не занижать общее число видео канала. ✅ Выполнено (`src/handlers/resources/YouTube/YouTubeChannel.py`).
  - Для YouTube channel извлекать метаданные с приоритетом вкладки `/videos` и переносить счетчики из нее, чтобы избежать ложных значений вида `🎬 Видео: 2` на главной вкладке канала. ✅ Выполнено (`src/handlers/resources/YouTube/YouTubeChannel.py`, `test/handlers/YouTube/test_youtube_channel_video_count.py`).
  - Для деплоя заменить принудительное завершение контейнера (`docker rm -f`) на graceful-остановку (`docker stop --time 25`) с последующим удалением, чтобы `on_shutdown` успевал отправлять сообщение «Бот выключается...». ✅ Выполнено (`manager.sh`).
  - Усилить `on_shutdown`: отправка уведомления администратору не зависит от успешности чтения чатов из БД; ошибки получения чатов и закрытия БД логируются отдельно без срыва отправки уведомления. ✅ Выполнено (`src/bot/lifespan/shutdown.py`).
  - Для Instagram profile добавить устойчивый fallback: при сбое `yt-dlp` extractor пробовать `web_profile_info` API по username и использовать канонический profile URL c завершающим `/`. ✅ Выполнено (`src/handlers/resources/Instagram/InstagramProfile.py`, `test/handlers/Instagram/test_instagram_profile_helpers.py`).
  - Для Instagram `media_group` исправить обработку каруселей: удалять `img_index` из URL, сохранять несколько фото/видео без перезаписи файлов и поддерживать дополнительные аудиофайлы (`audios`) в общем pipeline отправки/cleanup. ✅ Выполнено (`src/handlers/resources/Instagram/InstagramMediaGroup.py`, `src/handlers/mixins/media_group.py`, `src/bot/processing/media_processor.py`, `src/handlers/base.py`, `test/handlers/Instagram/test_instagram_media_group_helpers.py`, `test/handlers/test_cleanup_helpers.py`).
  - Для Instagram handlers добавить безопасный auto-режим cookies (`INSTAGRAM_COOKIES_ENABLED/INSTAGRAM_COOKIES_PATH`) и подключить его в stories/reels/media_group/profile; для stories добавить явный warning про возможную необходимость авторизации. ✅ Выполнено (`src/config.py`, `src/utils/cookies.py`, `src/handlers/resources/Instagram/InstagramHandler.py`, `src/handlers/resources/Instagram/InstagramStories.py`, `src/handlers/resources/Instagram/InstagramReels.py`, `src/handlers/resources/Instagram/InstagramMediaGroup.py`, `src/handlers/resources/Instagram/InstagramProfile.py`, `test/handlers/Instagram/test_instagram_cookies_helpers.py`).
  - Добавить runtime-поддержку COUB (`https://coub.com/view/<id>`) через единый pipeline handlers, включая регистрацию в `ServiceManager` и smoke-проверки по шаблону `test/handlers/<Source>`. ✅ Выполнено (`src/handlers/manager.py`, `src/handlers/resources/Coub/*`, `test/handlers/Coub/test_coub_handlers_local.py`, `test/handlers/Coub/Coub_urls.py`).
  - Для COUB video реализовать каскад источников `segments -> share -> file_versions/ytdlp`, валидацию `permalink == requested_id`, приоритет no-watermark пути через `segments` и fallback-деградацию без падения отправки. ✅ Выполнено (`src/handlers/resources/Coub/CoubVideo.py`).
  - Для COUB video выровнять длительность итогового MP4 по оригинальной аудиодорожке (audio-led): зацикливать видеоряд до длины аудио и подтверждать наличие audio/video потоков в smoke-проверке. ✅ Выполнено (`src/handlers/resources/Coub/CoubVideo.py`, `test/handlers/Coub/test_coub_handlers_local.py`).
  - Улучшить метод получения COUB video без watermark: усилить приоритет raw/segments-источников, расширить эвристику фильтрации branded/share URL и добавить диагностику выбранного source для ускоренного разбора проблемных кейсов.
  - Собирать `exceptions_per_hour`, `error_rate`, `handler_failure_rate`.
  - Вести топ ошибок по типу/источнику:
    - `ValueError`, `TelegramTimeoutError`, ошибки БД, ошибки загрузки контента.
  - Разделять ошибки по этапам:
    - resolve URL,
    - handler.process,
    - отправка в Telegram,
    - update_stats.
- Результат: быстрый поиск сломанных сценариев и инфраструктурных проблем.

### 8. Производительность обработки

- Статус (2026-03-07): открыто.
- Проблема: неизвестно, где тратится время (сеть, API, БД, хендлеры).
- Действие:
  - Мерить:
    - `response_time` (полный цикл обработки ссылки),
    - latency Telegram API вызовов,
    - время DB-операций,
    - `handler_execution_time` по каждому источнику.
  - Добавить агрегаты: avg / p95 / p99.
- Пример:
  - avg response time: 120ms
  - p95 response time: 420ms
- Результат: понятные точки оптимизации и SLO для бота.

### 9. Системные метрики контейнера/сервера

- Статус (2026-03-07): открыто.
- Проблема: без системных метрик тяжело увидеть деградацию до падений.
- Действие:
  - Собирать CPU, RAM, open file descriptors, network I/O.
  - Для async-нагрузки добавить event loop lag и размер очереди задач обработки.
  - Отслеживать число активных одновременных обработок (с учетом `Semaphore(3)`).
- Примечание: queue size в явном виде сейчас отсутствует в архитектуре, потребуется внедрение слоя очередей/метрик.
- Результат: раннее обнаружение перегрузок и узких мест.

### 10. Архитектурная карта проекта (Python/бот-контур)

- Статус (2026-03-07): открыто.
- Проблема: текущая архитектура понятна по коду, но нет единой визуальной схемы потока данных и ответственности модулей.
- Действие:
  - Зафиксировать карту уровня приложения (L1/L2), например:
    - `User -> Telegram API -> aiogram Bot/Dispatcher -> Routers -> Handlers -> DB layer`.
  - Для текущего проекта отдельно отметить точки:
    - `network calls`: `aiohttp` resolve URL, `yt-dlp`, Telegram API send methods, внешние API handlers;
    - `state transitions`: команды `/start`/`/stop` и toggle-команды (изменение `bot_enabled/errors_enabled/notifications_enabled`);
    - `data writes`: `update_stats`, `set_*_enabled`, создание/обновление записей в БД.
  - Добавить схему в отдельный md-файл (или секцию в `README`) и поддерживать вместе с архитектурными изменениями.
  - Проверить и зафиксировать цепочку формирования обработчиков: `mixins -> source_mixin -> source_Handler -> media_router`.
- Результат: быстрее ревью архитектуры, легче выявлять странности в маршруте данных.

### 11. Dependency graph модулей

- Статус (2026-03-07): открыто.
- Проблема: зависимости между модулями не визуализированы; сложно быстро увидеть избыточные связи.
- Действие:
  - Построить граф импортов для `src/` (например, `pydeps`/`snakefood`/`import-linter` + Graphviz).
  - Проверять и фиксировать желаемые уровни зависимостей:
    - `bot/commands`, `bot/processing` -> `handlers` / `utils` / `middlewares.db`
    - `handlers` -> `mixins` / `utils` / интеграции
    - `db.processing` -> `db.models` -> `db.core`
  - Для текущего проекта адаптировать слой `services/repositories`:
    - роль сервисного слоя частично выполняют `bot/processing` и `handlers/manager`;
    - роль repository-слоя частично выполняют `middlewares/db/processing`.
- Результат: прозрачные зависимости, меньше риска циклических импортов и сильной связности.

### 12. Метрики сложности кода

- Статус (2026-03-07): открыто.
- Проблема: без code metrics сложно понимать, какие модули становятся “горячими точками” техдолга.
- Действие:
  - Добавить измерение:
    - `cyclomatic complexity` (например, `radon cc`);
    - `maintainability index` (`radon mi`);
    - `lines per module` (`cloc`/`scc`);
    - `module coupling` (через import graph / lint rules).
  - Ввести пороговые значения и отчеты в CI для `dev`.
  - По покрытию тестами:
    - сейчас `tests/` в legacy-статусе;
    - метрику `test coverage` включать после возврата тестового контура.
- Результат: управляемый рост кода и раннее обнаружение переусложненных модулей.

### 13. Воронки сценариев (Flow analytics / conversion funnel)

- Статус (2026-03-07): открыто.
- Проблема: нет количественной картины, где пользователи “теряются” в сценариях использования.
- Действие:
  - Определить ключевые воронки, релевантные текущему боту:
    - команда `/start` -> отправка ссылки -> resolve URL -> обработка handler -> отправка результата;
    - входящее сообщение с URL -> `split_into_blocks` -> `get_handler` -> `process_block` -> success/fail;
    - команды управления (`/toggle_*`) -> изменение настройки -> подтверждение пользователю.
  - Для каждого шага считать вход/выход и drop-off.
  - Строить dashboard с этапами и конверсией по этапам.
- Пример:
  - start: 1000
  - sent_link: 800
  - resolved: 520
  - processed: 410
  - delivered: 400
- Результат: видно, где ломается UX/интеграции и что упрощать в первую очередь.

## Приоритет P3 (дальше)

### 14. Возврат к тестам как отдельная фаза

- Статус (2026-03-08): частично выполнено.
- Проблема: `tests/` сейчас legacy и не участвует в актуальном контуре.
- Действие:
  - При готовности вернуть минимальный smoke-набор:
    - startup/shutdown,
    - middleware gate,
    - базовая обработка URL.
  - Добавить локальный интеграционный сценарий проверки `TikTokHandler` на реальных ссылках (`video`, `profile`, `media_group`) с явным отчетом по результатам. ✅ Выполнено (`test/handlers/TikTok/test_tiktok_handlers_local.py`, проверка 3/3 успешна).
  - Реорганизовать прототип в `test/handlers/TikTok`: вынести тестовые URL в отдельный файл `TikTok_urls` с комментариями и использовать его как источник данных для smoke-теста handlers. ✅ Выполнено (`test/handlers/TikTok/TikTok_urls.py`).
  - Зафиксировать в `README.md` и `.github/ai_context.md`, что для будущих проверок работоспособности handlers используется прототип: `test/handlers/TikTok/test_tiktok_handlers_local.py` + `test/handlers/TikTok/TikTok_urls.py`. ✅ Выполнено.
  - Добавить отдельный smoke-тест `test/handlers/YouTube/test_youtube_handlers_local.py` и источник ссылок `test/handlers/YouTube/YouTube_urls.py` для кейсов `shorts`/`channel`. ✅ Выполнено.
  - Добавить отдельный smoke-тест `test/handlers/Instagram/test_instagram_handlers_local.py` и источник ссылок `test/handlers/Instagram/Instagram_urls.py` для кейсов `reels`/`media_group`/`stories`/`profile`. ✅ Выполнено.
  - Добавить отдельный smoke-тест `test/handlers/VK/test_vk_handlers_local.py` и источник ссылок `test/handlers/VK/VK_urls.py` для кейсов `audio`/`playlist` VK Music. ✅ Выполнено.
  - Зафиксировать единое правило именования источника тестовых ссылок как `<Source>_urls.py` для новых smoke-тестов handlers. ✅ Выполнено.
  - Перенести структуру локальных smoke-тестов handlers в единый путь `test/handlers/*`. ✅ Выполнено.
  - Обновить TikTok video smoke-ссылку на кейс `https://www.tiktok.com/t/ZP8XA8HA8/`, который воспроизводил ошибку формата. ✅ Выполнено (`test/handlers/TikTok/TikTok_urls.py`).
  - Добавить кейсы для interstitial-URL:
    - YouTube consent (absolute + relative `continue`) ✅ Выполнено (`test/handlers/YouTube/YouTube_urls.py`);
    - Instagram wrapped (absolute + relative `u`) ✅ Выполнено (`test/handlers/Instagram/Instagram_urls.py`).
  - Добавить в markdown-документацию правило-шаблон для будущих handler smoke-тестов (структура теста и обязательные шаги). ✅ Выполнено.
  - Перенести правило `Handler Smoke-Тестов` из `README.md` в `.github/ai_context.md` как контекстное правило для агентов. ✅ Выполнено.
  - Добавить правило эскалации: если скрипт/тулза не запускается из-за ограничений среды (sandbox/права/сеть), запрашивать повышение прав. ✅ Выполнено (`.github/ai_context.md`).
  - Убрать режим `--classify-only` из smoke-скриптов handlers и запускать их только в полном режиме обработки. ✅ Выполнено (`test/handlers/YouTube/test_youtube_handlers_local.py`, `test/handlers/Instagram/test_instagram_handlers_local.py`).
  - Зафиксировать правило запуска тестов: любые тесты (`pytest`, smoke-скрипты) выполнять только с повышенными правами после явного запроса пользователю. ✅ Выполнено (`README.md`, `.github/ai_context.md`).
  - Убрать `PytestCollectionWarning` в `test/handlers/*`:
    - переименовать dataclass-модели (`TestCase`, `TestResult`) в имена без префикса `Test` или явно исключить их из сбора pytest.
  - Разделить smoke-скрипты и unit-тесты по разным маскам запуска в CI, чтобы `pytest` не пытался автоматически собирать сценарные CLI-скрипты как тестовые классы.
  - Провести аудит fallback для TikTok caption после очистки хэштегов и гарантировать корректный fallback даже при пустом/невалидном title. ✅ Выполнено.
  - Запускать эти тесты в CI для `dev`.
- Результат: снижение регрессий при развитии функционала.

### 15. Гигиена проверок качества

- Статус (2026-03-07): открыто.
- Проблема: локальная проверка markdownlint цепляет `venv/Lib/site-packages/**/LICENSE.md` и дает шум, не относящийся к проектному коду.
- Действие:
  - Уточнить `.markdownlintignore` и/или команду запуска lint так, чтобы надежно исключать `venv/**` и другие внешние директории.
  - Зафиксировать в `README`/`.github/ai_context.md` каноническую команду lint только для поддерживаемых markdown-файлов репозитория.
  - Добавить отдельный check `python -m compileall src test` в CI как быстрый синтаксический smoke.
- Результат: предсказуемые проверки качества без ложных срабатываний и быстрее обратная связь в dev-потоке.

## Исключено из backlog (выполнено)

- Валидация env перед запуском деплоя. ✅
- Улучшение наблюдаемости деплоя. ✅
- Формализация release notes. ✅

## Рекомендуемый порядок внедрения

1. P0.1
2. P1.3 -> P1.2
3. P2.5 -> P2.6 -> P2.7
4. P2.8 -> P2.9
5. P2.10 -> P2.11
6. P2.12 -> P2.13
7. P2.4
8. P3.14 (когда команда вернется к тестовому контуру)
