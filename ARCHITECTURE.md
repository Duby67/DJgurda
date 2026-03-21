# Architecture

## Purpose

Этот файл дает короткую карту системы и маршрутизирует к более узким документам.

## System Summary

DJgurda Bot - асинхронный Telegram-бот для обработки медиа-ссылок в чатах. Пользователь отправляет ссылку, бот определяет источник, извлекает контент и отправляет результат в унифицированном формате обратно в чат.

Стабильный runtime-контур:

- TikTok
- YouTube
- Instagram
- COUB
- Yandex Music

Источник в статусе `in_development`:

- VK

## Core Runtime Flow

`Telegram update -> router -> media_router -> resolve_url -> HandlerRegistry/ServiceManager -> handler.process() -> MediaResult -> sender registry -> Telegram API`

## Current Architecture Boundary

- Рабочая boundary-модель опирается на typed result `MediaResult`.
- Stable runtime больше не должен опираться на broad legacy payload как на основной контракт.
- Stable gateways строятся вокруг composition-based services.
- Внешние источники считаются нестабильной внешней средой, а не надежной частью системы.

## Subsystems

- `src/bot/`
  - Telegram-роутеры, команды, orchestration, startup и shutdown.
- `src/handlers/`
  - registry, source handlers, media services и интеграционная логика.
- `src/middlewares/`
  - chat-state middleware и текущий DB access layer.
- `src/utils/`
  - URL helpers, message formatting, cookies, runtime storage и другие общие утилиты.
- `deploy/`
  - container packaging, deploy scripts и sync tooling.

## Key Entrypoints

- `src/main.py`
- `src/config.py`
- `src/bot/processing/media_router.py`
- `src/handlers/manager.py`
- `src/bot/lifespan/startup.py`
- `src/bot/lifespan/shutdown.py`

## Key Constraints

- Основной UX-контекст - mobile Telegram.
- Webhook-режим сейчас не реализован.
- `VK` не должен восприниматься как stable runtime-source.
- `tests/` и `test/` не являются общим source of truth, кроме согласованных handler smoke flows.

## Read Next

- `docs/design-docs/index.md`
- `docs/product-specs/index.md`
- `docs/RELIABILITY.md`
- `docs/SECURITY.md`
- `docs/PLANS.md`
