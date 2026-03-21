# AGENTS

## Purpose

Этот файл описывает локальные правила для зоны `src/middlewares/db/`.

## Scope

`src/middlewares/db/` отвечает за:

- DB core и session handling;
- модели;
- processing-слой для настроек и статистики.

## Read First

Перед изменениями в этой зоне сначала читать:

1. `src/middlewares/AGENTS.md`
2. `docs/RELIABILITY.md`
3. `docs/exec-plans/tech-debt-tracker.md`
4. конкретные файлы из `src/middlewares/db/`, связанные с задачей

## Local Invariants

- `core.py` задает базовые DB boundaries и не должен обрастать бизнес-логикой.
- `models/` должны оставаться декларативным описанием данных.
- `processing/` должен оставаться слоем операций, а не местом для Telegram-facing behavior.
- Конкурентные записи статистики и чтение chat settings являются high-risk зонами.

## High-Risk Areas

- silent fallback при ошибках чтения;
- конкурентное создание `Source`;
- частые чтения chat settings на горячем пути;
- неявное смешение repository/service semantics.

## Change Rules

- Не маскировать DB errors без явной наблюдаемости.
- Если вводится cache, upsert или retry behavior, это нужно отдельно описывать как изменение semantics.
- Не смешивать модельные изменения и поведение orchestration в одном неочевидном патче.
- Если rename слоя напрашивается архитектурно, сначала фиксировать policy и intent в docs.

## Test Guidance

- Для этой зоны важны целевые unit/integration checks, а не только smoke tests.
- Если изменение влияет на runtime flow, нужно смотреть и в `test/bot/processing/`.
- Любой запуск тестов требует явного подтверждения пользователя.

## Escalate When

- требуется изменение схемы данных;
- нужно менять конкуретное поведение записи статистики;
- изменение затрагивает и DB processing, и bot middleware semantics одновременно.
