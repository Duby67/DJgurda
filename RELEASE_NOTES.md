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
  - Для деплоя в `manager.sh` добавлена graceful-остановка контейнера перед удалением, чтобы `on_shutdown` успевал отправить уведомление о выключении.
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
  - Переработан `manager.sh`: добавлены явные шаги деплоя, preflight-проверки и единый формат логов.
  - Для `dev` в `manager.sh` отключен автоперезапуск контейнера (`--restart no`).
  - В `IMPROVEMENTS.md` обновлены статусы пунктов 1, 2, 3, 5, 7.
  - В `DEPLOY_LAYOUT.md` добавлено описание стадий деплоя.
- Важно для деплоя:
  - `manager.sh` теперь завершает деплой до `docker run`, если preflight не пройден.
  - `BOT_DB_PATH` должен быть `/app/src/data/db/bot.db`.
  - `YOUTUBE_COOKIES_PATH` должен быть `/app/src/data/cookies/youtube_cookies.txt`.
- Breaking changes:
  - Нет.
- Ручные действия после релиза:
  - Нет, если `.env` уже содержит обязательные ключи и ожидаемые пути.
