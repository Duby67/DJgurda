# DB Degradation Visibility

## Status

- Active.
- Discovery completed on 2026-03-24.
- Current phase: implementation planning.

## Goal

Сделать деградацию чтения chat settings из БД явной и предсказуемой вместо молчаливого схлопывания в defaults.

## Current Assessment

- Проблема подтверждена и остается актуальной.
- Ошибки чтения в settings flow сейчас маскируются под обычные defaults.
- Это меняет поведение runtime без явного operational signal: disabled chats могут начать обрабатываться, error messages могут исчезать, notification fanout может молча обнуляться.

## Evidence

- `src/middlewares/db/processing/bot_settings_processor.py`
- `src/middlewares/bot_enabled.py`
- `src/bot/processing/media_router.py`
- `src/bot/processing/media_processor.py`
- `src/bot/lifespan/startup.py`
- toggle commands в `src/bot/commands/`

## Main Areas

- `src/middlewares/db/processing/bot_settings_processor.py`
- `src/middlewares/bot_enabled.py`
- `src/bot/processing/media_router.py`
- `src/bot/processing/media_processor.py`
- `src/bot/lifespan/startup.py`
- `src/bot/commands/toggle_bot.py`
- `src/bot/commands/toggle_errors.py`
- `src/bot/commands/toggle_notifications.py`

## Action Plan

1. Разделить `settings missing` и `DB read failure` в settings processor.
2. Ввести явный contract для degraded settings read вместо plain bool fallback.
3. Явно выбрать fail-open/fail-closed поведение для bot-enabled middleware и связанных runtime paths.
4. Запретить toggle-командам инвертировать fallback-state, если текущий state неизвестен из-за DB failure.
5. Добавить targeted tests на degraded read semantics и command behavior under DB failure.

## Verification Notes

- Потребуются targeted tests вокруг settings processor, middleware и toggle commands.
- Запуск тестов требует отдельного approval пользователя.

## Swarm Notes

- Initial discovery orchestrated through swarm run `20260324-114634-swarm`.
- Следующий полезный increment: выбрать explicit degrade contract и закрепить его в implementation plan до code changes.
