# cookies-session-refresher local test

Локальный Docker-стенд для проверки cookies-session-refresher образа
без пуша на сервер.

## Где лежат локальные данные

Все runtime-данные стенда находятся прямо в
`test/docker/cookies-session-refresher/`:

- `FirefoxProfile/` - рабочий Firefox-профиль, который монтируется
  в контейнер и получает обновленные cookies-файлы;
- `FirefoxProfile.7z` - локальный backup того же профиля;
- `logs/` - логи локальных прогонов.

Файлы профиля, архивы и логи не должны попадать в git.

## Быстрый запуск

1. Убедитесь, что рабочий профиль лежит в
   `test/docker/cookies-session-refresher/FirefoxProfile`.
2. Запустите локальный прогон:

```powershell
.\test\docker\cookies-session-refresher\run_local_refresher.ps1
```

Скрипт пересобирает локальный образ из текущего кода репозитория и
запускает одноразовый контейнер `DJgurda-cookies-local`, который
работает напрямую с `FirefoxProfile/`.

## Кастомный путь к профилю

Если нужно использовать другую локальную папку профиля:

```powershell
.\test\docker\cookies-session-refresher\run_local_refresher.ps1 `
  -ProfileDir .\some\other\FirefoxProfile
```

## Кастомные URL

По умолчанию стенд открывает YouTube URL из compose-файла. Для
разового override можно передать `-RefreshTargets`:

```powershell
.\test\docker\cookies-session-refresher\run_local_refresher.ps1 `
  -RefreshTargets "https://www.youtube.com/,https://www.youtube.com/feed/subscriptions"
```
