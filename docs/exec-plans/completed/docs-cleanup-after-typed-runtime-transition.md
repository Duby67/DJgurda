# Docs Cleanup After Typed-Runtime Transition

## Status

- Completed on 2026-03-24.
- Docs/code alignment review and cleanup finished.

## Goal

Дочистить оставшиеся tracked docs и compatibility shims после typed-runtime transition так, чтобы public runtime ownership и typed contracts были описаны точно.

## Outcome

- Top-level runtime wording выровнен под текущий `ServiceManager -> handler.process() -> MediaResult` flow.
- Stale compatibility shim в typed contracts убран.
- Открытый backlog по typed-runtime cleanup на данный момент больше не требует отдельного active workstream.

## Evidence

- `ARCHITECTURE.md`
- `docs/design-docs/runtime-pipeline.md`
- `src/bot/processing/media_router.py`
- `src/handlers/manager.py`
- `src/handlers/registry.py`
- `src/handlers/contracts.py`

## Main Areas

- `ARCHITECTURE.md`
- `docs/design-docs/runtime-pipeline.md`
- `src/handlers/contracts.py`
- при необходимости связанные handler-layer docs/comments

## Landed Changes

1. Обновлены `ARCHITECTURE.md` и `docs/design-docs/runtime-pipeline.md`.
2. Убраны stale compatibility helpers из `src/handlers/contracts.py`.
3. Выполнен targeted sweep по tracked docs на ownership wording вокруг typed runtime.

## Verification Notes

- Code/doc alignment review закрыт.
- Изменения вошли в общий focused verification set.

## Swarm Notes

- Initial discovery orchestrated through swarm run `20260324-114634-swarm`.
- Работа завершена в рамках follow-up cleanup pass.
