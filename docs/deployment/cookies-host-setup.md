# Подготовка хоста для cookies-extractor (Ubuntu 24)

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

## 3) Подготовить Firefox профиль с авторизациями

```bash
firefox --no-remote --profile ~/firefox_profile \
  https://www.youtube.com \
  https://vk.com \
  https://www.instagram.com \
  https://www.tiktok.com \
  https://coub.com
```

В открывшемся окне войдите в аккаунты на всех 5 платформах и полностью закройте Firefox.

## 4) Дождаться CI/CD доставки runtime-файлов

После успешного запуска workflow `build-cookies.yml` в `~/cookies/runtime` должны появиться:
- `compose.cookies.yml`
- `run_cookies_extractor.sh`

Проверьте:

```bash
ls -la ~/cookies/runtime
```

## 5) Тестовый запуск контейнера

```bash
~/cookies/runtime/run_cookies_extractor.sh
```

## 6) Проверить результаты

```bash
ls -la ~/cookies/YouTube ~/cookies/VK ~/cookies/Instagram ~/cookies/TikTok ~/cookies/Coub
```

## 7) Добавить cron

```bash
crontab -e
```

Используйте пример из `deploy/cron/cookies.cron.example`.
