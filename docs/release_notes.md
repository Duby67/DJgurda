# Release Notes

## Как вести release notes

Для каждого заметного изменения добавляй новую секцию по шаблону:

```md
## YYYY-MM-DD | version/tag: <значение> | env: <dev/prod/both>
- Что изменилось:
  - ...
- Важно для деплоя:
  - ...
- Breaking changes:
  - Нет / Да (описание)
- Ручные действия после релиза:
  - Нет / Да (описание)
```

## 2026-03-11 | version/tag: v1.2.4 | env: prod

- Что изменилось:
  - Версия бота повышена с `1.2.3` до `1.2.4`.
  - Релизные артефакты синхронизированы с текущим номером версии по проектной процедуре.
- Важно для деплоя:
  - При публикации релиза использовать tag `v1.2.4` на этом же commit.
- Breaking changes:
  - Нет.
- Ручные действия после релиза:
  - Нет.

## 2026-03-09 | version/tag: v1.2.3 | env: prod

- Что изменилось:
  - Версия бота повышена с `1.2.2` до `1.2.3`.
  - В runtime `ServiceManager` временно отключен `VKHandler` (режим `DEV-only`).
  - В `deploy/manager.sh` добавлен шаг резервного копирования базы данных перед перезапуском контейнера.
  - В `deploy/manager.sh` включена ротация резервных копий БД через `DB_BACKUP_KEEP_COUNT` (по умолчанию `14`).
  - В проектной документации восстановлена читаемая UTF-8 кодировка и закреплены правила: запрет удаленного доступа для AI-агента и использование UTF-8 без BOM.
- Важно для деплоя:
  - Убедиться, что у пользователя запуска есть права на `$HOME/bot_{env}/data/db/backups`.
  - При необходимости настроить `DB_BACKUP_KEEP_COUNT` в окружении (`0` отключает удаление старых бэкапов).
  - Учесть, что VK-ссылки в `prod` не обрабатываются до повторного включения `VKHandler`.
- Breaking changes:
  - Да: в `prod` временно отключена обработка VK Music.
- Ручные действия после релиза:
  - Если требуется VK в `prod`, включить `VKHandler` только после отдельной smoke-проверки и согласования.

## 2026-03-09 | version/tag: infra-deploy-cookies-layout | env: both

- Что изменилось:
  - Docker ignore перенесен из корня в `deploy/Dockerfile.dockerignore` рядом с `deploy/Dockerfile`.
  - Для deploy введен явный staging-каталог `deploy/cookies`; в репозитории хранится только `deploy/cookies/.gitkeep`.
  - Все `*_cookies.txt` добавлены в `.gitignore`, чтобы исключить случайную утечку cookies из публичного репозитория.
  - GitHub Actions materializes `deploy/cookies` на runner из secrets и перед запуском `deploy/manager.sh` синхронизирует файлы в `$HOME/bot_{env}/data/cookies` с перезаписью.
  - Обновлены `README.md`, `.github/ai-context.md`, `docs/deploy_layout.md` и `docs/repository-root-map.md` под трехуровневую схему `local/cookies -> deploy/cookies -> src/data/cookies`.
- Важно для деплоя:
  - Для deploy должны быть заданы secrets `YOUTUBE_COOKIES_FILE`, `INSTAGRAM_COOKIES_FILE`, `TIKTOK_COOKIES_FILE`, `VK_COOKIES_FILE`, `COUB_COOKIES_FILE` хотя бы для одного актуального `*_cookies.txt`.
  - Если после materialize в `deploy/cookies` нет ни одного `*_cookies.txt`, workflow завершится ошибкой.
- Breaking changes:
  - Нет.
- Ручные действия после релиза:
  - При локальной ручной загрузке cookies на сервер использовать `deploy/cookies`, а не `local/cookies`.

## 2026-03-10 | version/tag: infra-deploy-cookie-sync | env: both

- Что изменилось:
  - Deploy workflows больше не завершаются ошибкой, если secrets с cookies не заданы.
  - При отсутствии secrets deploy сохраняет текущие cookies в `$HOME/bot_{env}/data/cookies` и продолжает использовать server-side volume без изменений.
  - При наличии secrets workflow перезаписывает только одноименные `*_cookies.txt`, не удаляя отсутствующие файлы из runtime-директории сервера.
  - Ручная синхронизация cookies перенесена в deploy-контур: добавлены `deploy/sync_cookies.sh` и `deploy/sync_cookies.bat`.
  - Ручные sync-скрипты загружают только локально существующие `*_cookies.txt` и не удаляют cookies, которых нет локально.
- Важно для деплоя:
  - Реальные cookies по-прежнему не должны попадать в git; в репозитории хранится только `deploy/cookies/.gitkeep`.
  - Для обновления cookies через CI secrets `YOUTUBE_COOKIES_FILE`, `INSTAGRAM_COOKIES_FILE`, `TIKTOK_COOKIES_FILE`, `VK_COOKIES_FILE`, `COUB_COOKIES_FILE` являются опциональными.
- Breaking changes:
  - Нет.
- Ручные действия после релиза:
  - Для ручной синхронизации cookies использовать `deploy/sync_cookies.sh` или `deploy/sync_cookies.bat`.

## 2026-03-10 | version/tag: infra-deploy-cookie-sync-config | env: both

- Что изменилось:
  - Параметры ручной синхронизации cookies (`REMOTE_USER`, `REMOTE_HOST`, `REMOTE_PORT`) вынесены из `deploy/sync_cookies.sh` и `deploy/sync_cookies.bat` в локальный `deploy/sync_cookies.env`.
  - В репозиторий добавлен шаблон `deploy/sync_cookies.env.example`.
  - `deploy/sync_cookies.env` добавлен в `.gitignore` и не должен попадать в git.
- Важно для деплоя:
  - Перед первым ручным запуском sync-скриптов нужно создать `deploy/sync_cookies.env` из `deploy/sync_cookies.env.example`.
- Breaking changes:
  - Нет.
- Ручные действия после релиза:
  - Заполнить локальный `deploy/sync_cookies.env` актуальными значениями подключения.

## 2026-03-08 | version/tag: v1.2.2 | env: prod

- Что изменилось:
  - Версия бота повышена с `1.2.1` до `1.2.2`.
  - Добавлена и стабилизирована поддержка COUB (`/view/<id>`) в основном runtime pipeline.
  - Для COUB реализован каскад источников `segments -> share -> file_versions/ytdlp` с приоритетом пути для минимизации watermark.
  - Для COUB добавлена обязательная валидация `permalink == requested_id` для защиты от API-mismatch кейсов.
  - Добавлен и актуализирован локальный smoke-тест обработчика COUB с кейсом `https://coub.com/view/480igm`.
- Важно для деплоя:
  - Для наилучшего результата (видео+аудио и приоритет no-watermark пути) `ffmpeg` должен быть доступен в `PATH`.
  - При отсутствии `ffmpeg` обработчик использует безопасные fallback-источники, но итоговый ролик может быть с watermark.
- Breaking changes:
  - Нет.
- Ручные действия после релиза:
  - Проверить наличие `ffmpeg` на сервере (`ffmpeg -version`).

## 2026-03-07 | version/tag: v1.2.1 | env: prod

- Что изменилось:
  - Версия бота повышена с `1.2.0` до `1.2.1`.
  - Для YouTube cookies внедрен безопасный режим: использование только при `YOUTUBE_COOKIES_ENABLED=true`, заглушечные файлы автоматически игнорируются.
  - Улучшена обработка YouTube/Instagram interstitial URL, включая относительные `continue/u` ссылки.
  - Для YouTube channel исправлен расчет `🎬 Видео`: приоритет отдан `channel_video_count`/`video_count`, `playlist_count` оставлен как fallback.
  - Для деплоя в `deploy/manager.sh` добавлена graceful-остановка контейнера перед удалением, чтобы `on_shutdown` успевал отправить уведомление о выключении.
- Важно для деплоя:
  - Локальный release-проход делался в ветке `dev`; перед финальным релизом в `main` требуется синхронизация `dev` с `origin/dev` и стандартный merge-flow.
  - При использовании YouTube cookies убедись, что выставлены оба параметра: `YOUTUBE_COOKIES_ENABLED=true` и корректный `YOUTUBE_COOKIES_PATH`.
- Breaking changes:
  - Нет.
- Ручные действия после релиза:
  - Проверить `.env` на наличие `YOUTUBE_COOKIES_ENABLED` (по умолчанию `false`).

## 2026-03-07 | version/tag: infra-local-update | env: both

- Что изменилось:
  - Обновлен `.gitignore`: добавлены структурированные секции для локальных секретов, Python-кеша/сборки, IDE, логов и OS-временных файлов.
  - Переработан `deploy/manager.sh`: добавлены явные шаги деплоя, preflight-проверки и единый формат логов.
  - Для `dev` в `deploy/manager.sh` отключен автоперезапуск контейнера (`--restart no`).
  - В `docs/improvements.md` обновлены статусы пунктов 1, 2, 3, 5, 7.
  - В `docs/deploy_layout.md` добавлено описание стадий деплоя.
- Важно для деплоя:
  - `deploy/manager.sh` теперь завершает деплой до `docker run`, если preflight не пройден.
  - `BOT_DB_PATH` должен быть `/app/src/data/db/bot.db`.
  - `YOUTUBE_COOKIES_PATH` должен быть `/app/src/data/cookies/www.youtube.com_cookies.txt`.
- Breaking changes:
  - Нет.
- Ручные действия после релиза:
  - Нет, если `.env` уже содержит обязательные ключи и ожидаемые пути.
