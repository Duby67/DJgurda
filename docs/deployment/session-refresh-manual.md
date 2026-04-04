# Ручной запуск session-refresh: пошагово

Этот документ описывает 2 ручных сценария:

- запуск контейнера с хоста через
  `~/cookies/runtime/run_session_refresher.sh`;
- запуск контейнерного wrapper внутри контейнера через
  `/session_refresher/refresh_session.sh`.

Для первичного запуска нужен архив профиля
`deploy/local/firefox_profile.tar.gz`.

## 1) Передать архив на хост

С локальной машины:

```bash
scp -P 228 deploy/local/firefox_profile.tar.gz \
  <SSH_USER>@<SSH_HOST>:~/cookies/runtime/firefox_profile.tar.gz
```

Для Windows PowerShell используйте аналогичный `scp`
с Windows-путем.

## 2) Восстановить профиль и очистить кеш/ссылки

На сервере:

```bash
~/cookies/runtime/prepare_firefox_profile.sh \
  ~/cookies/runtime/firefox_profile.tar.gz \
  ~/firefox_profile
```

Первый аргумент — путь к архиву профиля, второй аргумент —
путь к директории Firefox-профиля на хосте.

Скрипт автоматически:

- распакует архив,
- удалит lock-файлы (`.parentlock`, `.startup-incomplete`, `lock`),
- удалит кеш-папки (`cache2`, `startupCache`, `crashes`, `minidumps`),
- удалит символические ссылки,
- удалит `*.sqlite-shm` и `*.sqlite-wal`.

## 3) Установить необходимые пакеты на хосте

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin cron
sudo systemctl enable --now docker
```

## 4) Проверить список источников

```bash
cat ~/cookies/runtime/refresh_sources.list
```

Формат строки: `source|folder|urls`.
Поле `urls` содержит одну или несколько ссылок,
разделенных `;`.

## 5) Ручной запуск контейнера с хоста

```bash
~/cookies/runtime/run_session_refresher.sh
```

Хостовый wrapper делает только host-level работу:

- создает/обновляет backup профиля
  `~/cookies/runtime/firefox_profile.backup.tar.gz`,
- восстанавливает и очищает основной профиль через
  `~/cookies/runtime/prepare_firefox_profile.sh` из свежего
  backup-архива,
- собирает отдельный Selenium-profile
  `~/firefox_selenium_profile` через
  `~/cookies/runtime/prepare_selenium_profile.sh`,
- разбирает `refresh_sources.list`, создает `~/cookies/<folder>`
  и собирает очередь URL,
- запускает контейнер `DJgurda-cookies` от UID/GID
  текущего пользователя.

Дальше внутри контейнера `refresh_session.sh` поднимает
Xvfb/DBus и запускает `refresh_session.py`, который
последовательно открывает URL и обновляет cookie в
примонтированном `~/firefox_selenium_profile`, после чего
хостовый wrapper переносит обновленные cookie/storage файлы
обратно в `~/firefox_profile`.

Если нужно вручную собрать Selenium-profile:

```bash
~/cookies/runtime/prepare_selenium_profile.sh \
  ~/firefox_profile \
  ~/firefox_selenium_profile
```

Timezone контейнера берется с хоста через `/etc/localtime`
и `/etc/timezone`.

## 6) Проверить, что профиль меняется и не блокируется root

```bash
ls -la ~/firefox_profile | head
```

## 7) Ручной запуск wrapper внутри контейнера

Если нужно проверить именно контейнерный runtime-wrapper без
хостового `run_session_refresher.sh`, запустите контейнер
через compose:

```bash
docker compose -f ~/cookies/runtime/compose.cookies-refresh.yml \
  run --rm --name DJgurda-cookies cookies-session-refresher
```

Контейнер создается с именем `DJgurda-cookies`, а `CMD`
образа автоматически вызывает
`/session_refresher/refresh_session.sh`.

## 8) Автоматический запуск контейнера через cron

```bash
crontab -e
```

Добавьте строку из `~/cookies/runtime/cookies.cron.example`.
Cron будет запускать тот же
`~/cookies/runtime/run_session_refresher.sh`.

## 9) Как контейнер попадает на сервер

Это делает CI/CD workflow `build-cookies.yml`:

- собирает образ `:cookies-refresh`,
- публикует его в GHCR,
- копирует runtime-скрипты в `~/cookies/runtime`,
- выполняет `docker pull` на сервере.
