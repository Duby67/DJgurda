# Подготовка хоста для session-refresher (Ubuntu 24)

## 1) Создать директории

```bash
mkdir -p ~/cookies/runtime
mkdir -p ~/firefox_profile
mkdir -p ~/logs
```

## 2) Выдать безопасные права

```bash
chmod 700 ~/firefox_profile
chmod 755 ~/cookies ~/cookies/runtime ~/logs
```

## 3) Дождаться CI/CD доставки runtime-файлов

После успешного запуска `build-cookies.yml` в `~/cookies/runtime` должны появиться:
- `compose.cookies-refresh.yml`
- `run_session_refresher.sh`
- `prepare_firefox_profile.sh`
- `cookies.cron.example`

Проверка:

```bash
ls -la ~/cookies/runtime
```

## 4) Восстановить Firefox профиль из архива

```bash
~/cookies/runtime/prepare_firefox_profile.sh ~/cookies/runtime/firProf.tar.gz ~/firefox_profile
```

## 5) Тестовый запуск автообновления сессии

```bash
~/cookies/runtime/run_session_refresher.sh
```

## 6) Проверить состояние профиля

```bash
ls -la ~/firefox_profile | head
```

## 7) Добавить cron вручную (опционально)

```bash
crontab -e
```

Используйте пример из `~/cookies/runtime/cookies.cron.example` только после ручной валидации.
