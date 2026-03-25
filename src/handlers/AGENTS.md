# AGENTS

## Purpose

Этот файл описывает локальные правила для слоя `src/handlers/`.

## Scope

`src/handlers/` отвечает за:

- runtime registry и manager;
- typed contracts;
- source handlers в `resources/`;
- shared infrastructure в `infrastructure/`.

## Read First

Перед изменениями в этом модуле сначала читать:

1. корневой `AGENTS.md`
2. `ARCHITECTURE.md`
3. `docs/design-docs/runtime-pipeline.md`
4. `docs/RELIABILITY.md`
5. конкретные файлы source handler-а или registry, которые реально участвуют в задаче

## Local Invariants

- Runtime registry должен оставаться декларативным.
- Новые runtime handlers добавляются через `registry.py`, а не через скрытые side effects.
- Stable и non-runtime sources должны оставаться явно разделенными.
- Source-specific logic должна жить внутри своего source-модуля или общего infrastructure-слоя, но не размазываться по другим подсистемам.
- Active runtime boundary не должен возвращаться к broad legacy payload assumptions.

## Change Rules

- При изменении `registry.py` или `manager.py` нужно явно оценивать влияние на весь stable runtime.
- При добавлении нового source или content type нужно обновлять:
  - registry;
  - source-status policy;
  - целевые tests/smoke checks;
  - релевантные docs.
- Изменения вокруг `VK` требуют отдельной оценки cookie-sensitive и network-sensitive рисков для всего active runtime.
- Предпочитать shared infrastructure только там, где это реально уменьшает дублирование без потери ясности source behavior.

## Test Guidance

- Source-level проверки в основном лежат в `test/handlers/`.
- Для стабильных handlers важны локальные smoke paths и cleanup временных файлов.
- Любой запуск тестов требует явного подтверждения пользователя.

## Escalate When

- нужно менять `MediaResult`, `ContentType` или другие typed contracts;
- требуется расширение stable runtime source list;
- изменение затрагивает одновременно несколько source-модулей и shared infrastructure.

## Read Next

- `src/bot/AGENTS.md`
- `test/AGENTS.md`
