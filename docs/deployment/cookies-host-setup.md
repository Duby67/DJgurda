# Подготовка хоста для session-refresher (Ubuntu 24)

## 1) Создать директории

```bash
mkdir -p ~/cookies/runtime
mkdir -p ~/firefox_profile
mkdir -p ~/logs/cookies
```

## 2) Выдать безопасные права

```bash
chmod 700 ~/firefox_profile
chmod 755 ~/cookies ~/cookies/runtime ~/logs ~/logs/cookies
```

## 3) Дождаться CI/CD доставки runtime-файлов

После успешного запуска `build-cookies.yml`
в `~/cookies/runtime` должны появиться:

- `compose.cookies-refresh.yml`
- `run_session_refresher.sh`
- `refresh_sources.list`
- `cookies.cron.example`

Проверка:

```bash
ls -la ~/cookies/runtime
```

## 4) При необходимости передать архив профиля на хост

Поддерживаемые форматы:

- `*.tar.gz`
- `*.tgz`
- `*.tar`
- `*.7z` при установленном `7z`/`7za`

Пример:

```bash
scp ./FirefoxProfile.7z <SSH_USER>@<SSH_HOST>:~/cookies/runtime/FirefoxProfile.7z
```

## 5) Тестовый запуск автообновления сессии

Без замены профиля:

```bash
~/cookies/runtime/run_session_refresher.sh
```

С заменой профиля из архива:

```bash
~/cookies/runtime/run_session_refresher.sh ~/cookies/runtime/FirefoxProfile.7z
```

Хостовый wrapper теперь делает только host-level шаги:

- создает ротационный backup текущего `~/firefox_profile`;
- при переданном архиве полностью разворачивает его в
  `~/firefox_profile`;
- разбирает `refresh_sources.list`, создает `~/cookies/<folder>`
  и собирает очередь URL;
- запускает контейнер `DJgurda-cookies` от UID/GID
  текущего пользователя.

Очистка lock/cache/session/sqlite-sidecar файлов теперь всегда
происходит только внутри контейнера через
`prepare_runtime_profile.sh`.

## 6) Проверить состояние профиля

```bash
ls -la ~/firefox_profile | head
```

## 7) Проверить логи

```bash
ls -la ~/logs/cookies
```

## 8) Добавить cron вручную (опционально)

```bash
crontab -e
```

Используйте пример из `~/cookies/runtime/cookies.cron.example`
только после ручной валидации.
