# Подготовка хоста для session-refresher (Ubuntu 24)

## 1) Создать директории

```bash
mkdir -p ~/cookies/runtime
mkdir -p ~/firefox_profile
mkdir -p ~/firefox_selenium_profile
mkdir -p ~/logs/cookies
```

## 2) Выдать безопасные права

```bash
chmod 700 ~/firefox_profile ~/firefox_selenium_profile
chmod 755 ~/cookies ~/cookies/runtime ~/logs ~/logs/cookies
```

## 3) Дождаться CI/CD доставки runtime-файлов

После успешного запуска `build-cookies.yml`
в `~/cookies/runtime` должны появиться:

- `compose.cookies-refresh.yml`
- `run_session_refresher.sh`
- `prepare_firefox_profile.sh`
- `prepare_selenium_profile.sh`
- `refresh_sources.list`
- `cookies.cron.example`

Проверка:

```bash
ls -la ~/cookies/runtime
```

## 4) Восстановить основной Firefox профиль из архива

```bash
~/cookies/runtime/prepare_firefox_profile.sh \
  ~/cookies/runtime/firefox_profile.tar.gz \
  ~/firefox_profile
```

Если нужно вручную собрать Selenium-profile:

```bash
~/cookies/runtime/prepare_selenium_profile.sh \
  ~/firefox_profile \
  ~/firefox_selenium_profile
```

## 5) Тестовый запуск автообновления сессии

```bash
~/cookies/runtime/run_session_refresher.sh
```

`run_session_refresher.sh` сам создаст папки `~/cookies/<folder>`,
соберет отдельный `~/firefox_selenium_profile`, запустит контейнер
`DJgurda-cookies` и после успешного прогона синхронизирует
cookie/storage файлы обратно в `~/firefox_profile`.

## 6) Проверить состояние профилей

```bash
ls -la ~/firefox_profile | head
ls -la ~/firefox_selenium_profile | head
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
