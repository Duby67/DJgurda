# Cron

На сервере используется `cron` для периодических задач cookies-extractor.

Базовый подход:
- CI/CD заранее доставляет свежий образ `cookies-extractor` на сервер (`docker pull`).
- CI/CD автоматически копирует runtime-файлы в `~/cookies/runtime`.
- cron вызывает `~/cookies/runtime/run_cookies_extractor.sh`.
- скрипт запускает `docker compose` с `~/cookies/runtime/compose.cookies.yml`.
- `compose.cookies.yml` использует готовый образ из GHCR (по умолчанию тег `cookies`).
- cookies и Firefox-профиль монтируются из домашней директории пользователя (`${HOME}`).
- один запуск обновляет cookies для: YouTube, VK, Instagram, TikTok, Coub.
- логирование ведется в `$HOME/logs/cookies_extractor.log`.
- при ошибке обновления используется предыдущий валидный cookie-файл.
