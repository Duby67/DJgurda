# Политика cookies

## Локальная разработка

- Все файлы вида `*_cookies.txt` игнорируются git.
- Для локальных тестов используется `deploy/local/cookies/`.

## Сервер

На сервере базовая структура:
- `/home/DJgurda/bot_dev`
- `/home/DJgurda/bot_prod`

Папка с cookies:
- `/home/DJgurda/DJgurda/cookies`

Именно с этой папкой взаимодействует контейнер `cookies-extractor`.
