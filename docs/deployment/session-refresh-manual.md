# Ручной запуск session-refresh: пошагово

Этот документ нужен для первичного ручного запуска, когда у вас уже есть архив профиля `deploy/local/firProf.tar.gz`.

## 1) Передать архив на хост

С локальной машины:

```bash
scp -P 228 deploy/local/firProf.tar.gz <SSH_USER>@<SSH_HOST>:~/cookies/runtime/firProf.tar.gz
```

Для Windows PowerShell используйте аналогичный `scp` с Windows-путем.

## 2) Восстановить профиль и очистить кеш/ссылки

На сервере:

```bash
~/cookies/runtime/prepare_firefox_profile.sh ~/cookies/runtime/firProf.tar.gz ~/firefox_profile
```

Скрипт автоматически:
- распакует архив,
- удалит lock-файлы (`.parentlock`, `.startup-incomplete`, `lock`),
- удалит кеш-папки (`cache2`, `startupCache`, `crashes`, `minidumps`),
- удалит символические ссылки,
- удалит `*.sqlite-shm` и `*.sqlite-wal`.

## 3) Установить необходимые системные пакеты (если сервер "чистый")

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin cron
sudo systemctl enable --now docker
```

## 4) Настроить и проверить стек

Одноразовый refresh:

```bash
~/cookies/runtime/run_session_refresher.sh
```

Одноразовый extractor:

```bash
~/cookies/runtime/run_cookies_extractor.sh
```

Полный pipeline (refresh -> extract):

```bash
~/cookies/runtime/run_refresh_then_extract.sh
```

## 5) Проверить, что появились новые файлы

```bash
ls -la ~/cookies/YouTube ~/cookies/VK ~/cookies/Instagram ~/cookies/TikTok ~/cookies/Coub
```

## 6) Автоматизация через cron

```bash
crontab -e
```

Добавьте строку из `~/cookies/runtime/cookies.cron.example`.

## 7) Как контейнер попадает на сервер

Это делает CI/CD workflow `build-cookies.yml`:
- собирает образы `:cookies` и `:cookies-refresh`,
- публикует их в GHCR,
- копирует runtime-скрипты в `~/cookies/runtime`,
- выполняет `docker pull` на сервере.
