# Политика cookies

Контур `cookies-extractor` используется только для удаленного запуска на сервере.

## Сервер

На сервере базовая структура:
- `~/bot_dev`
- `~/bot_prod`

Папки, необходимые для cookies-extractor:
- `~/cookies/YouTube` - выходные cookie-файлы YouTube.
- `~/firefox_profile` - Firefox профиль с авторизацией YouTube.

Именно с этими папками взаимодействует контейнер `cookies-extractor`.
