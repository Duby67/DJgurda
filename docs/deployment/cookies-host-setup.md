# Подготовка хоста для cookies-extractor (Ubuntu 24)

## 1) Создать директории

```bash
mkdir -p ~/cookies/YouTube
mkdir -p ~/firefox_profile
mkdir -p ~/logs
```

## 2) Выдать безопасные права

```bash
chmod 700 ~/firefox_profile
chmod 755 ~/cookies ~/cookies/YouTube
```

## 3) Подготовить Firefox профиль с авторизацией YouTube

```bash
firefox --no-remote --profile ~/firefox_profile https://youtube.com
```

В открывшемся окне войдите в аккаунт YouTube и полностью закройте Firefox.

## 4) Тестовый запуск контейнера

```bash
cd ~/bot_prod
/usr/bin/docker compose -f deploy/compose/compose.cookies.yml run --rm cookies-extractor
```

## 5) Добавить cron

```bash
crontab -e
```

Используйте пример из `deploy/cron/cookies.cron.example`.
