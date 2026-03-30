# Политика cookies

Контур `cookies` в текущей версии состоит из одного сервиса:
- `cookies-session-refresher` - автообновление Firefox-профиля.

## Сервер

На сервере базовая структура может содержать:
- `~/bot-dev`
- `~/bot-prod`

Cookies-контур автономен и работает только с:
- `~/cookies/runtime` (runtime-файлы)
- `~/firefox_profile` (профиль Firefox)
- `~/logs` (логи запуска)

Контур `cookies` не должен изменять файлы и директории `~/bot-dev` и `~/bot-prod`.
