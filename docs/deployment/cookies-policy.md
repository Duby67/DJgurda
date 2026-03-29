# Политика cookies

Контур `cookies-extractor` используется только для удаленного запуска на сервере.

## Сервер

На сервере базовая структура:
- `~/bot_dev`
- `~/bot_prod`

Папки, необходимые для cookies-extractor:
- `~/cookies/YouTube` - выходные cookie-файлы YouTube.
- `~/cookies/VK` - выходные cookie-файлы VK.
- `~/cookies/Instagram` - выходные cookie-файлы Instagram.
- `~/cookies/TikTok` - выходные cookie-файлы TikTok.
- `~/cookies/Coub` - выходные cookie-файлы Coub.
- `~/firefox_profile` - Firefox профиль с авторизацией на всех платформах.

Именно с этими папками взаимодействует контейнер `cookies-extractor`.
