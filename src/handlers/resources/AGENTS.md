# AGENTS

## Purpose

Этот файл описывает локальные правила для зоны `src/handlers/resources/`.

## Scope

`src/handlers/resources/` содержит source-specific runtime logic:

- URL services;
- dependencies;
- source handlers;
- source-level processors и extraction flows.

## Read First

Перед изменениями в этой зоне сначала читать:

1. `src/handlers/AGENTS.md`
2. `docs/design-docs/runtime-pipeline.md`
3. `docs/RELIABILITY.md`
4. конкретный source-модуль, затронутый задачей

## Local Invariants

- Каждый source должен быть максимально самодостаточным внутри своей папки.
- Source-specific эвристики не должны протекать в соседние sources.
- Shared behavior нужно выносить только туда, где это не размывает ownership source-модуля.
- Stable runtime sources и development-only sources должны оставаться явно различимыми.
- Runtime temp files, cookies и внешние API считать потенциально нестабильной частью каждого source flow.

## Change Rules

- Не копировать паттерны из одного source в другой без проверки, что они действительно общие.
- При изменении URL classification или extraction logic учитывать влияние на smoke tests этого source.
- Если меняется `PATTERN`, `content_type` detection или fallback chain, нужно явно фиксировать ожидаемое поведение.
- Не повышать локальную эвристику до shared policy без проверки нескольких sources.

## Test Guidance

- Основные source-level проверки находятся в `test/handlers/<Source>/`.
- Для env/cookies-dependent changes важно учитывать local smoke setup и cleanup.
- Любой запуск тестов требует явного подтверждения пользователя.

## Escalate When

- изменение требует затронуть несколько source-папок;
- хочется вынести новую общую abstraction в `src/handlers/infrastructure/`;
- задача меняет source-status policy или stable runtime list.
