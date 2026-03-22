# AGENTS

## Purpose

Этот файл описывает локальные правила для слоя `src/bot/`.

## Scope

`src/bot/` отвечает за Telegram-facing behavior:

- команды в `commands/`;
- orchestration и routing в `processing/`;
- startup/shutdown lifecycle в `lifespan/`.

## Read First

Перед изменениями в этом модуле сначала читать:

1. корневой `AGENTS.md`
2. `ARCHITECTURE.md`
3. `docs/RELIABILITY.md`
4. файлы в `src/bot/`, которые реально участвуют в задаче

## Local Invariants

- Bot-слой должен координировать обработку, а не содержать source-specific extraction logic.
- Активный runtime-flow должен опираться на typed result `MediaResult`, а не на broad legacy payload assumptions.
- Поведение команд должно оставаться локальным для текущего чата, если нет явного требования на глобальное поведение.
- Lifecycle-код должен оставаться согласованным с runtime storage, DB init и shutdown cleanup.
- При изменениях в `processing/` важно сохранять детерминированность multi-link orchestration.

## Change Rules

- Если меняется `media_router.py` или `media_processor.py`, нужно отдельно проверить влияние на:
  - удаление исходного сообщения;
  - обработку unsupported/failed blocks;
  - тексты ошибок и reply behavior.
- Не переносить в `src/bot/` логику, которая должна жить в `src/handlers/` или `src/utils/`.
- Не дублировать source-status knowledge в командах и роутерах без явной причины.

## Test Guidance

- Основные целевые тесты для этого слоя лежат в `test/bot/processing/`.
- Если изменение затрагивает orchestration между bot и handlers, могут понадобиться и handler smoke checks.
- Любой запуск тестов требует явного подтверждения пользователя.

## Escalate When

- задача требует менять контракт `MediaResult` или sender selection;
- нужно менять handler selection или source-status policy;
- изменение выходит за пределы `src/bot/` и требует правок в DB layer или handlers.

## Read Next

- `src/handlers/AGENTS.md`
- `src/middlewares/AGENTS.md`
- `test/AGENTS.md`
