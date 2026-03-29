# Подготовка хоста для cookies-extractor (Ubuntu 24)

## 1) Создать директории

```bash
mkdir -p ~/cookies
mkdir -p ~/firefox-profile
mkdir -p ~/logs
```

## 2) Выдать безопасные права

```bash
chmod 700 ~/firefox-profile
chmod 755 ~/cookies
```

## 3) Подготовить Firefox профиль с авторизацией YouTube

```bash
firefox --no-remote --profile ~/firefox-profile https://youtube.com
```

В открывшемся окне войдите в аккаунт YouTube и полностью закройте Firefox.

## 4) Подготовить env-файл для compose

```bash
cp ~/bot_prod/deploy/compose/cookies.env.example ~/bot_prod/deploy/compose/.env.cookies
```

## 5) Тестовый запуск контейнера

```bash
cd ~/bot_prod
/usr/bin/docker compose --env-file deploy/compose/.env.cookies -f deploy/compose/compose.cookies.yml run --rm cookies-extractor
```

## 6) Добавить cron

```bash
crontab -e
```

Используйте пример из `deploy/cron/cookies.cron.example`.
