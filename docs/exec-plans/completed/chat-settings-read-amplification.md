# Chat Settings Read Amplification

## Status

- Completed on 2026-03-24.

## Outcome

- `bot_settings_processor` теперь использует bounded per-update snapshot cache для chat settings вместо повторных независимых read-запросов в рамках одного update.
- `BotEnabledMiddleware` открывает cache scope на границе update flow, поэтому downstream processing reuse-ит тот же snapshot без нового global state.
- Write-path обновляет cached snapshot внутри текущего scope, чтобы после `set_*` не оставались stale reads.

## Verification

- `.\venv\Scripts\python.exe -m pytest test/bot/middlewares/test_bot_settings_degradation.py test/bot/commands/test_toggle_settings_degradation.py test/bot/processing/test_media_router_multi_link.py test/bot/processing/test_media_processor_errors.py test/handlers/test_cleanup_helpers.py -q`
- Result: `19 passed`

## Notes

- Repo-local swarm run `20260324-132128-swarm` дошёл до coder/tester artifacts и снова упёрся только в infra-level `docker_version_probe_failed`.
- Изменение намеренно осталось bounded: source of truth по settings не переносился в новый global cache/service layer, а `get_chats_with_notifications_enabled()` и toggle pre-read path не переводились на долгоживущий cache.
