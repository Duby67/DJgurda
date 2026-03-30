# Политика cookies

Контур `cookies` предназначен для удаленного запуска на сервере и состоит из двух сервисов:
- `cookies-extractor` - выгрузка cookies в `*_cookies.txt`.
- `cookies-session-refresher` - автообновление Firefox-профиля.

## Сервер

На сервере базовая структура может содержать:
- `~/bot-dev`
- `~/bot-prod`

Контур `cookies` автономен и работает только в пределах `~/cookies`.

Папки и файлы, необходимые для cookies-контура:
- `~/cookies/runtime` - runtime-файлы, которые автоматически доставляет CI/CD.
- `~/cookies/YouTube` - выходные cookie-файлы YouTube.
- `~/cookies/VK` - выходные cookie-файлы VK.
- `~/cookies/Instagram` - выходные cookie-файлы Instagram.
- `~/cookies/TikTok` - выходные cookie-файлы TikTok.
- `~/cookies/Coub` - выходные cookie-файлы Coub.
- `~/firefox_profile` - Firefox профиль с авторизацией.

Контур `cookies` не должен изменять файлы и директории `~/bot-dev` и `~/bot-prod`.
