# Политика cookies

Контур `cookies-extractor` используется только для удаленного запуска на сервере.

## Сервер

На сервере базовая структура может содержать:
- `~/bot-dev`
- `~/bot-prod`

Контур cookies-extractor автономен и работает только в пределах `~/cookies`.

Папки, необходимые для cookies-extractor:
- `~/cookies/runtime` - runtime-файлы (`compose.cookies.yml` и `run_cookies_extractor.sh`), которые автоматически доставляет CI/CD.
- `~/cookies/YouTube` - выходные cookie-файлы YouTube.
- `~/cookies/VK` - выходные cookie-файлы VK.
- `~/cookies/Instagram` - выходные cookie-файлы Instagram.
- `~/cookies/TikTok` - выходные cookie-файлы TikTok.
- `~/cookies/Coub` - выходные cookie-файлы Coub.
- `~/firefox_profile` - Firefox профиль с авторизацией на всех платформах.

Контур cookies-extractor не должен изменять файлы и директории `~/bot-dev` и `~/bot-prod`.
