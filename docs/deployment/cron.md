# Cron

На сервере используется `cron` для периодических задач.

Базовый подход:
- cron вызывает `deploy/cron/run_cookies_extractor.sh`.
- скрипт запускает `docker compose` с `deploy/compose/compose.cookies.yml` и `.env.cookies`.
- cookies и firefox-профиль монтируются из домашней директории пользователя (`${HOME}`).
- логирование в отдельный файл с ротацией.
- при ошибке обновления используется предыдущий валидный cookie-файл.
