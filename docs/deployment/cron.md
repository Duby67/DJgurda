# Cron

На сервере используется `cron` для периодических задач cookies-контура.

Базовый подход:
- CI/CD заранее доставляет свежие образы `cookies` и `cookies-refresh` на сервер (`docker pull`).
- CI/CD автоматически копирует runtime-файлы в `~/cookies/runtime`.
- cron вызывает `~/cookies/runtime/run_refresh_then_extract.sh`.
- скрипт сначала выполняет `run_session_refresher.sh`, затем (после паузы) `run_cookies_extractor.sh`.
- оба контейнера запускаются от UID/GID пользователя хоста, поэтому новые файлы создаются не от `root`.
- логирование ведется в `$HOME/logs/cookies_extractor.log`.
