# DB Degradation Visibility

## Status

- Completed on 2026-03-24.
- Implementation and focused verification finished.

## Goal

Сделать деградацию чтения chat settings из БД явной и предсказуемой вместо молчаливого схлопывания в defaults.

## Outcome

- Деградация чтения settings больше не маскируется под обычные defaults.
- Runtime paths теперь явно различают settings missing и DB read failure.
- Toggle-команды перестали инвертировать неизвестное состояние при сломанном settings read.

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

## Landed Changes

1. В `src/middlewares/db/processing/bot_settings_processor.py` введен explicit `SettingsReadError`.
2. Middleware, processing и lifespan paths теперь явно обрабатывают degraded settings reads.
3. Toggle-команды останавливаются с понятным сообщением вместо unsafe inversion.
4. Добавлены focused tests на middleware degradation, startup/shutdown notification behavior и toggle command behavior.

## Verification Notes

- Пройдены targeted tests вокруг settings processor, middleware, lifespan и toggle commands.
- Verification закрыт в проектном `venv`.

## Swarm Notes

- Initial discovery orchestrated through swarm run `20260324-114634-swarm`.
- Работа завершена в рамках follow-up implementation pass и verification boundary.
