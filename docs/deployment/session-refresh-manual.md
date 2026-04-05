# Ручной запуск session-refresh: пошагово

Этот документ описывает 2 ручных сценария:

- запуск контейнера с хоста через
  `~/cookies/runtime/run_session_refresher.sh`;
- запуск контейнерного wrapper внутри контейнера через
  `/session_refresher/refresh_session.sh`.

Для первичного запуска можно использовать архив профиля
`FirefoxProfile.7z` или `firefox_profile.tar.gz`.

## 1) Передать архив на хост

С локальной машины:

```bash
scp -P 228 ./FirefoxProfile.7z \
  <SSH_USER>@<SSH_HOST>:~/cookies/runtime/FirefoxProfile.7z
```

Для Windows PowerShell используйте аналогичный `scp`
с Windows-путем.

## 2) Установить необходимые пакеты на хосте

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin cron
sudo systemctl enable --now docker
```

Для `*.7z` архивов дополнительно:

```bash
sudo apt-get install -y p7zip-full
```

## 3) Проверить список источников

```bash
cat ~/cookies/runtime/refresh_sources.list
```

Формат строки: `source|folder|urls`.
Поле `urls` содержит одну или несколько ссылок,
разделенных `;`.

## 4) Ручной запуск контейнера с хоста

Без замены профиля:

```bash
~/cookies/runtime/run_session_refresher.sh
```

С заменой профиля из архива:

```bash
~/cookies/runtime/run_session_refresher.sh \
  ~/cookies/runtime/FirefoxProfile.7z
```

Хостовый wrapper делает только host-level работу:

- создает/обновляет backup профиля
  `~/cookies/runtime/firefox_profile.backup.tar.gz`;
- при переданном архиве полностью разворачивает его в
  `~/firefox_profile`;
- разбирает `refresh_sources.list`, создает `~/cookies/<folder>`
  и собирает очередь URL;
- запускает контейнер `DJgurda-cookies` от UID/GID
  текущего пользователя.

Дальше внутри контейнера `refresh_session.sh` поднимает
Xvfb/DBus и запускает `refresh_session.py`, а обязательный
`prepare_runtime_profile.sh` очищает lock/session/cache/
sqlite-sidecar файлы уже внутри примонтированного
`~/firefox_profile`.

Timezone контейнера берется с хоста через `/etc/localtime`
и `/etc/timezone`.

## 5) Проверить, что профиль меняется и не блокируется root

```bash
ls -la ~/firefox_profile | head
```

## 6) Ручной запуск wrapper внутри контейнера

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

## 7) Автоматический запуск контейнера через cron

```bash
crontab -e
```

Добавьте строку из `~/cookies/runtime/cookies.cron.example`.
Cron будет запускать тот же
`~/cookies/runtime/run_session_refresher.sh`.

## 8) Как контейнер попадает на сервер

Это делает CI/CD workflow `build-cookies.yml`:

- собирает образ `:cookies-refresh`,
- публикует его в GHCR,
- копирует runtime-скрипты в `~/cookies/runtime`,
- выполняет `docker pull` на сервере.
