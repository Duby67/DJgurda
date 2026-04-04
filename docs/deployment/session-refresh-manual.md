# Ручной запуск session-refresh: пошагово

Этот документ нужен для первичного ручного запуска,
когда у вас есть архив профиля
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

## 5) Проверить ручной запуск refresher

```bash
~/cookies/runtime/run_session_refresher.sh
```

Во время запуска скрипт:

- разберет `refresh_sources.list` и соберет очередь URL,
- создаст `~/cookies/<folder>` для каждого источника,
- создаст/обновит backup профиля
  `~/cookies/runtime/firefox_profile.backup.tar.gz`,
- запустит single-process Firefox через Selenium + geckodriver,
- пройдет URL последовательно с случайной длительностью на шаг,
- запустит контейнер от UID/GID текущего пользователя.

## 6) Проверить, что профиль меняется и не блокируется root

```bash
ls -la ~/firefox_profile | head
```

## 7) Автоматизация через cron (по вашему решению)

```bash
crontab -e
```

Добавьте строку из `~/cookies/runtime/cookies.cron.example`.

## 8) Как контейнер попадает на сервер

Это делает CI/CD workflow `build-cookies.yml`:

- собирает образ `:cookies-refresh`,
- публикует его в GHCR,
- копирует runtime-скрипты в `~/cookies/runtime`,
- выполняет `docker pull` на сервере.
