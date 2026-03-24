# Runtime Ownership Of Service Manager

## Status

- Completed on 2026-03-24.

## Outcome

- `ServiceManager` теперь владеет runtime lookup policy через `resolve_handler(raw_url, resolved_url)`, а `media_router` больше не дублирует raw/resolved fallback у себя.
- `media_router` сохранён как orchestration/preflight слой: он делает `resolve_url`, готовит block context и передаёт handler дальше в `process_block`.
- Runtime docs теперь явно фиксируют, что `HandlerRegistry` является source of truth для active runtime composition, а `ServiceManager` остаётся thin lookup-wrapper, а не execution orchestrator.

## Verification

- `.\venv\Scripts\python.exe -m pytest test/bot/processing -q`
- `.\venv\Scripts\python.exe -m pytest test/handlers/test_cleanup_helpers.py -q`
- Result: `14 passed`

## Notes

- Repo-local swarm run `20260324-135451-swarm` дошёл до coder/tester artifacts и честно собрал apply/verification bundle.
- Sandbox stage снова упёрся только в infra-level `sandbox_blocked` на `docker`, а не в проблему correctness change-set.
