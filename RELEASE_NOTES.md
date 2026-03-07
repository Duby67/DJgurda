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
