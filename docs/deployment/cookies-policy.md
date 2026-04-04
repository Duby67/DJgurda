# Политика cookies

Контур `cookies` в текущей версии состоит из одного сервиса:

- `cookies-session-refresher` - автообновление Firefox-профиля
  в контейнере `DJgurda-cookies`.

## Сервер

На сервере базовая структура может содержать:

- `~/bot-dev`
- `~/bot-prod`

Cookies-контур автономен и работает только с:

- `~/cookies/runtime` (runtime-файлы)
- `~/cookies/<folder>` (папки из `refresh_sources.list`)
- `~/firefox_profile` (основной Firefox-профиль)
- `~/firefox_selenium_profile` (отдельный профиль для Selenium-прогона)
- `~/logs/cookies` (логи запуска и cron)

Контур `cookies` не должен изменять файлы и директории
`~/bot-dev` и `~/bot-prod`.
