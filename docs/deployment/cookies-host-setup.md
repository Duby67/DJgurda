# Подготовка хоста для cookies-контура (Ubuntu 24)

## 1) Создать директории

```bash
mkdir -p ~/cookies/runtime
mkdir -p ~/cookies/YouTube ~/cookies/VK ~/cookies/Instagram ~/cookies/TikTok ~/cookies/Coub
mkdir -p ~/firefox_profile
mkdir -p ~/logs
```

## 2) Выдать безопасные права

```bash
chmod 700 ~/firefox_profile
chmod 755 ~/cookies ~/cookies/runtime ~/cookies/YouTube ~/cookies/VK ~/cookies/Instagram ~/cookies/TikTok ~/cookies/Coub
```

## 3) Дождаться CI/CD доставки runtime-файлов

После успешного запуска `build-cookies.yml` в `~/cookies/runtime` должны появиться:
- `compose.cookies.yml`
- `compose.cookies-refresh.yml`
- `run_cookies_extractor.sh`
- `run_session_refresher.sh`
- `run_refresh_then_extract.sh`
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

## 6) Тестовый запуск экстрактора

```bash
~/cookies/runtime/run_cookies_extractor.sh
```

## 7) Проверить владельца файлов

```bash
ls -la ~/cookies/YouTube ~/cookies/VK ~/cookies/Instagram ~/cookies/TikTok ~/cookies/Coub
```

Файлы должны принадлежать вашему пользователю, а не `root`.

## 8) Добавить cron

```bash
crontab -e
```

Используйте пример из `~/cookies/runtime/cookies.cron.example`.
