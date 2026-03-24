# Atomic Stats Updates

## Status

- Completed on 2026-03-24.
- Implementation and focused verification finished.

## Goal

Сделать stats flow атомарным при конкурентных обновлениях и перестать терять `Source`/`Stats` updates из-за race conditions.

## Outcome

- Stats flow переведен на atomic SQLite upsert path.
- Риск silent undercounting из-за read-then-write race conditions существенно снижен.
- Focused coverage теперь проверяет both sequential и concurrent update scenarios.

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

## Landed Changes

1. `Source` resolution переведен на atomic create-or-reuse flow.
2. `Stats` creation/increment переведен на single upsert с SQL-side increment.
3. Exception handling в stats path стал более явным для contention/DB failures.
4. Добавлены focused tests на sequential и concurrent updates.

## Verification Notes

- Пройдены targeted tests на sequential и concurrent stats updates.
- Verification закрыт в проектном `venv`.

## Swarm Notes

- Initial discovery orchestrated through swarm run `20260324-114634-swarm`.
- Работа завершена в рамках follow-up implementation pass и verification boundary.
