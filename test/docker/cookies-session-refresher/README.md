# cookies-session-refresher local test

Локальный Docker-стенд для проверки cookies-session-refresher образа
без пуша на сервер.

## Где лежат локальные данные

Все runtime-данные стенда находятся прямо в
`test/docker/cookies-session-refresher/`:

- `FirefoxProfile/` - рабочий Firefox-профиль, который монтируется
  в контейнер и получает обновленные cookies-файлы;
- `FirefoxProfile.7z` - локальный backup того же профиля;
- `refresh_sources.list` - локальный список URL для прогона;
- `smoke_check_local_refresher.py` - локальная проверка результата
  по итоговому логу;
- `logs/` - логи локальных прогонов.

Файлы профиля, архивы и логи не должны попадать в git.

## Быстрый запуск

1. Убедитесь, что рабочий профиль лежит в
   `test/docker/cookies-session-refresher/FirefoxProfile`.
2. При необходимости отредактируйте
   `test/docker/cookies-session-refresher/refresh_sources.list`.
3. Запустите локальный прогон:

```powershell
.\test\docker\cookies-session-refresher\run_local_refresher.ps1
```

Скрипт пересобирает локальный образ из текущего кода репозитория,
читает URL из `refresh_sources.list`, запускает одноразовый
контейнер `DJgurda-cookies-local`, а затем автоматически
выполняет smoke-check по итоговому логу.

Smoke-check подтверждает минимум следующее:

- `health_verdict=healthy`;
- `auth_verdict=authenticated`;
- `youtube_auth_cookies_after status=ok`;
- `cookies_compare domain=youtube.com status=changed`.

## Кастомный путь к профилю

Если нужно использовать другую локальную папку профиля:

```powershell
.\test\docker\cookies-session-refresher\run_local_refresher.ps1 `
  -ProfileDir .\some\other\FirefoxProfile
```

## Кастомные URL

Если нужно разово переопределить URL без изменения
`refresh_sources.list`, передайте `-RefreshTargets`:

```powershell
.\test\docker\cookies-session-refresher\run_local_refresher.ps1 `
  -RefreshTargets "https://www.youtube.com/,https://www.youtube.com/feed/subscriptions"
```

## Ручной smoke-check

Если нужно отдельно проверить уже существующий лог:

```powershell
.\venv\Scripts\python.exe `
  .\test\docker\cookies-session-refresher\smoke_check_local_refresher.py `
  .\test\docker\cookies-session-refresher\logs\session_refresher.latest.log
```
