# Docs Cleanup After Typed-Runtime Transition

## Status

- Active.
- Discovery completed on 2026-03-24.
- Current phase: scoped cleanup planning.

## Goal

Дочистить оставшиеся tracked docs и compatibility shims после typed-runtime transition так, чтобы public runtime ownership и typed contracts были описаны точно.

## Current Assessment

- Проблема остается актуальной, но уже в более узком виде, чем в tracker wording.
- Typed runtime уже является реальным runtime contract.
- Оставшийся долг сосредоточен вокруг неточной ownership wording в runtime docs.

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

## Action Plan

1. Обновить runtime docs так, чтобы public flow описывался как `ServiceManager -> handler.process() -> MediaResult`.
2. Перенести `HandlerRegistry` в описание implementation detail, а не в top-level ownership flow.
3. Сделать targeted sweep по tracked docs/comments на dual handler-selection ownership и obsolete legacy-compatibility wording.
4. После cleanup сузить формулировку backlog item, чтобы она отражала текущий реальный scope.

## Verification Notes

- Для docs cleanup достаточно code/doc alignment review.
- Если дойдём до удаления compatibility shim, понадобятся targeted code-level checks после отдельного approval.

## Swarm Notes

- Initial discovery orchestrated through swarm run `20260324-114634-swarm`.
- Следующий полезный increment: docs-first cleanup pass по remaining ownership wording.
