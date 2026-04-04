# cookies-session-refresher local test

Локальный Docker-стенд для проверки cookies-session-refresher образа
без пуша на сервер.

## Где лежат локальные данные

Все runtime-данные стенда находятся в `local/`:

- `local/firefox_profile.tar.gz` - входной архив профиля Firefox;
- `local/firefox_selenium_profile/` - профиль, который монтируется
  в контейнер;
- `local/logs/` - логи локальных прогонов.

Файлы из `local/` не должны попадать в git.

## Быстрый запуск

1. Положите архив профиля в
   `test/docker/cookies-session-refresher/local/firefox_profile.tar.gz`.
2. Запустите локальный прогон:

```powershell
.\test\docker\cookies-session-refresher\run_local_refresher.ps1
```

Скрипт пересобирает локальный образ из текущего кода репозитория,
готовит `local/firefox_selenium_profile` из архива и запускает
одноразовый контейнер `DJgurda-cookies-local`.

## Повторный прогон без пересборки профиля

Если нужно не пересоздавать профиль из архива, а прогнать контейнер
на уже существующем `local/firefox_selenium_profile`, используйте:

```powershell
.\test\docker\cookies-session-refresher\run_local_refresher.ps1 -SkipProfilePrepare
```

## Кастомные URL

По умолчанию стенд открывает YouTube URL из compose-файла. Для
разового override можно передать `-RefreshTargets`:

```powershell
.\test\docker\cookies-session-refresher\run_local_refresher.ps1 `
  -RefreshTargets "https://www.youtube.com/,https://www.youtube.com/feed/subscriptions"
```
