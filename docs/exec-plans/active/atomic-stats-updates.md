# Atomic Stats Updates

## Status

- Active.
- Discovery completed on 2026-03-24.
- Current phase: implementation planning.

## Goal

Сделать stats flow атомарным при конкурентных обновлениях и перестать терять `Source`/`Stats` updates из-за race conditions.

## Current Assessment

- Проблема подтверждена и остается актуальной.
- Текущий flow использует read-then-write и Python-side increment без atomic upsert.
- Operational impact: статистика может silently недосчитаться даже при успешной пользовательской отправке.

## Evidence

- `src/middlewares/db/processing/stats_processor.py`
- `src/middlewares/db/models/sources.py`
- `src/middlewares/db/models/stats.py`
- `src/middlewares/db/core.py`
- call site в `src/bot/processing/media_processor.py`

## Main Areas

- `src/middlewares/db/processing/stats_processor.py`
- `src/middlewares/db/models/sources.py`
- `src/middlewares/db/models/stats.py`

## Action Plan

1. Заменить select-then-insert flow для `Source` на DB-level upsert semantics.
2. Перевести `Stats` creation/increment на один atomic upsert с SQL-side increment.
3. Сузить exception handling и сделать contention/integrity failures отдельным operational signal.
4. Сохранить весь stats update внутри одной транзакции без Python-side read-modify-write ветвления.
5. Добавить targeted concurrency coverage для first-create и repeated increment scenarios.

## Verification Notes

- Нужны targeted tests на concurrent first-write и concurrent increment behavior.
- Запуск тестов требует отдельного approval пользователя.

## Swarm Notes

- Initial discovery orchestrated through swarm run `20260324-114634-swarm`.
- Следующий полезный increment: implementation plan под SQLite/SQLAlchemy upsert path без расширения scope в unrelated DB areas.
