# Подготовка хоста для cookies-extractor (Ubuntu 24)

## 1) Создать директории

```bash
mkdir -p ~/cookies/YouTube ~/cookies/VK ~/cookies/Instagram ~/cookies/TikTok ~/cookies/Coub
mkdir -p ~/firefox_profile
mkdir -p ~/logs
```

## 2) Выдать безопасные права

```bash
chmod 700 ~/firefox_profile
chmod 755 ~/cookies ~/cookies/YouTube ~/cookies/VK ~/cookies/Instagram ~/cookies/TikTok ~/cookies/Coub
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

## 4) Тестовый запуск контейнера

```bash
cd ~/bot_prod
/usr/bin/docker compose -f deploy/compose/compose.cookies.yml run --rm cookies-extractor
```

## 5) Проверить результаты

```bash
ls -la ~/cookies/YouTube ~/cookies/VK ~/cookies/Instagram ~/cookies/TikTok ~/cookies/Coub
```

## 6) Добавить cron

```bash
crontab -e
```

Используйте пример из `deploy/cron/cookies.cron.example`.
