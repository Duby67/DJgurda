# Cron

На сервере используется `cron` для периодических запусков
session-refresher.

Базовый подход:

- CI/CD заранее доставляет свежий образ `cookies-refresh`
  на сервер (`docker pull`).
- CI/CD автоматически копирует runtime-файлы в `~/cookies/runtime`.
- `~/cookies/runtime/run_session_refresher.sh` читает
  `~/cookies/runtime/refresh_sources.list`.
- Формат `refresh_sources.list`: `source|folder|urls`.
- Поле `urls` содержит одну или несколько ссылок,
  разделенных `;`.
- Контейнер проходит URL последовательно.
- На каждый URL выбирается случайная длительность
  в диапазоне `REFRESH_URL_DURATION_MIN..REFRESH_URL_DURATION_MAX`
  (по умолчанию `30..60` секунд).
- Перед запуском контейнера скрипт создает папки
  `~/cookies/<folder>` для каждого источника.
- По расписанию запускается
  `~/cookies/runtime/run_session_refresher.sh`.
- Контейнер запускается от UID/GID пользователя хоста.
  Поэтому новые файлы и папки принадлежат `DJgurda`,
  а профиль не блокируется root-владельцем.
- Подробные логи запуска пишутся в
  `$HOME/logs/cookies/session_refresher_<timestamp>.log`.
- Актуальный лог дублируется в
  `$HOME/logs/cookies/session_refresher.latest.log`.
- Вывод `cron` пишется в `$HOME/logs/cookies/cron.log`.
- В примере `crontab` добавлен `mkdir -p`, чтобы запуск не падал,
  если папка логов отсутствовала до старта задания.

Важно: `crontab` настраивается вручную
после валидации ручного запуска.
