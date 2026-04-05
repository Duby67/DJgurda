# Cron

На сервере `cron` запускает контейнерный session-refresher
через единый хостовый wrapper
`~/cookies/runtime/run_session_refresher.sh`.

## Цепочка запуска

- CI/CD заранее доставляет свежий образ `cookies-refresh`
  на сервер (`docker pull`) и копирует runtime-файлы в
  `~/cookies/runtime`.
- Образ `cookies-refresh` уже содержит Firefox, geckodriver
  и Python-зависимости из `requirements-cookies.txt`,
  установленные в системный Python контейнера.
- Cron вызывает `~/cookies/runtime/run_session_refresher.sh`.
- Этот же хостовый wrapper используется для ручного запуска
  контейнера с хоста.
- `run_session_refresher.sh` сначала делает backup
  `~/firefox_selenium_profile` в
  `~/cookies/runtime/firefox_profile.backup.tar.gz`, затем
  вызывает `~/cookies/runtime/prepare_firefox_profile.sh
  <archive_path> <profile_dir>`, читает
  `~/cookies/runtime/refresh_sources.list`, собирает
  `REFRESH_TARGETS` и запускает контейнер `DJgurda-cookies`
  через `docker compose run --rm --name DJgurda-cookies
  cookies-session-refresher`.
- Внутри контейнера `refresh_session.sh` поднимает Xvfb/DBus
  и запускает `refresh_session.py`.
- Timezone контейнера берется с хоста через bind-mount
  `/etc/localtime` и `/etc/timezone`.
- `refresh_session.py` последовательно открывает URL в одном
  Firefox-окне, выполняет легкие `scroll/hover` действия,
  обновляет `cookies.sqlite` в примонтированном профиле и
  пишет два итоговых статуса:
  `health_verdict=healthy|degraded|failed` и
  `auth_verdict=authenticated|partial|unauthenticated|
  blocked|n/a`.

## Источники URL

- `~/cookies/runtime/run_session_refresher.sh` читает
  `~/cookies/runtime/refresh_sources.list`.
- Формат `refresh_sources.list`: `source|folder|urls`.
- Поле `urls` содержит одну или несколько ссылок,
  разделенных `;`.
- На каждый URL выбирается случайная длительность
  в диапазоне `REFRESH_URL_DURATION_MIN..REFRESH_URL_DURATION_MAX`
  (по умолчанию `60..70` секунд).

## Файлы и права

- Перед запуском контейнера скрипт создает папки
  `~/cookies/<folder>` для каждого источника.
- Перед запуском контейнера скрипт делает один ротационный
  backup Selenium-профиля Firefox в
  `~/cookies/runtime/firefox_profile.backup.tar.gz`
  (поверх старого).
- Контейнер запускается от UID/GID пользователя хоста.
  Поэтому новые файлы и папки принадлежат `DJgurda`,
  а профиль не блокируется root-владельцем.

## Логи

- Подробные логи запуска пишутся в
  `$HOME/logs/cookies/session_refresher_<timestamp>.log`.
- Актуальный лог дублируется в
  `$HOME/logs/cookies/session_refresher.latest.log`.
- Вывод `cron` пишется в `$HOME/logs/cookies/cron.log`.

Важно: `crontab` настраивается вручную после валидации
ручного запуска.
